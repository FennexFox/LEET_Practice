from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REVIEWS_DIR = ROOT / "data" / "reviews"
CANONICAL_DIR = ROOT / "data" / "canonical"
OUT_DIR = ROOT / "data" / "tagging"
HOLDOUT_RECORDS = {
    "data/reviews/2025 추리논증 짝수형/q09.review.json",
    "data/reviews/2025 추리논증 짝수형/q23.review.json",
    "data/reviews/2025 추리논증 짝수형/q29.review.json",
    "data/reviews/2025 추리논증 짝수형/q33.review.json",
    "data/reviews/2025 추리논증 짝수형/q34.review.json",
}
HOLDOUT_REASON = (
    "No user self-review or assistant feedback is available. The user chose not to "
    "reconstruct the old reasoning from memory; this item should be re-solved later "
    "and then re-reviewed."
)
HOLDOUT_REVISIT_PLAN = "resolve_after_retake"


@dataclass(frozen=True)
class Assignment:
    primary: str
    secondary: tuple[str, ...]
    confidence: str
    note: str
    needs_review: bool = False
    needs_review_reason: str | None = None


TAG_DEFS: dict[str, dict[str, str]] = {
    "RELATION_DIRECTION_REVERSAL": {
        "ko": "관계 방향 전도",
        "definition": "A→B, 원인→결과, 주는 사람→받는 사람, 현재→목표, 입력→출력처럼 방향성이 명시된 관계를 반대로 잡은 오류.",
        "positive": "화살표, 비교 방향, 수식 대상, 교환·보상·통제의 방향이 실제 선지 판단에서 뒤집혔을 때 사용한다.",
        "negative": "명칭과 실제 속성을 혼동한 경우에는 TABLE_DIAGRAM_ENCODING_ERROR나 TEXTUAL_REDEFINITION_MISSED를 우선한다. 보완/대체 같은 방식어 오독은 TEXTUAL_REDEFINITION_MISSED를 우선한다.",
        "neighbors": "TABLE_DIAGRAM_ENCODING_ERROR는 표·기호·변수 입력 자체가 흔들릴 때, TEXTUAL_REDEFINITION_MISSED는 지문식 정의나 방식어를 다른 뜻으로 처리했을 때 우선한다.",
        "rule": "방향어가 나오면 `A -> B` 형식으로 다시 쓰고, 선지가 같은 방향을 보존하는지 확인한다.",
    },
    "ROLE_ATTRIBUTION_ERROR": {
        "ko": "역할·입장 귀속 오류",
        "definition": "주장, 비판, 관점, 행위자, 통제 대상, 견해의 공통점 등을 잘못된 사람·집단·입장에 귀속한 오류.",
        "positive": "A에게만 있는 술어를 B에도 붙이거나, 제3자에게 작용하는 규칙을 목표 대상에게 직접 작용한다고 본 경우 사용한다.",
        "negative": "같은 행위자의 조건 범위를 넓힌 경우에는 SCOPE_CONDITION_MISAPPLICATION을 우선한다.",
        "neighbors": "CONCEPT_LAYER_CONFUSION은 층위 자체가 바뀔 때, ROLE_ATTRIBUTION_ERROR는 귀속 대상이 바뀔 때 쓴다.",
        "rule": "선지마다 `누가 / 무엇을 / 어떤 입장으로` 말하는지 세 칸으로 분리한다.",
    },
    "SCOPE_CONDITION_MISAPPLICATION": {
        "ko": "범위·조건 오적용",
        "definition": "조건, 예외, 한계, 상한·하한, 제도 영역, 단서, 적용 범위를 과확장·과축소하거나 누락한 오류.",
        "positive": "예외 생략, 일부 조건만으로 강한 결론 도출, 가능성을 보장으로 읽기, 이상/이하 경계값 누락에 사용한다.",
        "negative": "조건은 알았으나 여러 문항 전체에 끝까지 들고 가지 못한 경우에는 GLOBAL_CONSTRAINT_DROPPED를 우선한다.",
        "neighbors": "TEXTUAL_REDEFINITION_MISSED는 지문이 용어 자체를 새로 정의했을 때, FORMAL_CONDITION_ERROR는 형식 논리·대수 조건 조작이 핵심일 때 쓴다.",
        "rule": "선지의 결론 앞에 필요한 조건을 모두 붙여 보고, 하나라도 빠지면 답 후보에서 제외한다.",
    },
    "TEXTUAL_REDEFINITION_MISSED": {
        "ko": "지문 정의 전환 누락",
        "definition": "지문이 개념·용어·기준을 특수하게 정의했는데 일반적 의미나 이전 의미로 처리한 오류.",
        "positive": "인정, 복종, 대체, 제3자, 업무수탁자처럼 지문 안 정의가 선지 판단의 기준일 때 사용한다.",
        "negative": "용어 정의는 보존했지만 조건 일부를 놓친 경우에는 SCOPE_CONDITION_MISAPPLICATION을 우선한다.",
        "neighbors": "CONCEPT_LAYER_CONFUSION은 정의보다 층위 구분이 핵심일 때 쓴다.",
        "rule": "핵심 용어 옆에 지문식 정의를 짧게 붙이고, 일상어 의미로 대체하지 않는다.",
    },
    "CONCEPT_LAYER_CONFUSION": {
        "ko": "개념 층위 혼동",
        "definition": "대상과 표상, 결과와 정당화, 내용 관련 이유와 태도 관련 이유, 구체 사례와 추상 원리처럼 층위가 다른 개념을 섞은 오류.",
        "positive": "좋은 결과와 관점의 정당화 방식, 현상 발생과 특정 원인, 상상력과 개념적 사유처럼 층위 전환이 핵심일 때 사용한다.",
        "negative": "층위보다 단순 귀속 대상이 문제이면 ROLE_ATTRIBUTION_ERROR를 우선한다.",
        "neighbors": "ARGUMENT_STRUCTURE_INCOMPLETE는 논증 단계 누락, CONCEPT_LAYER_CONFUSION은 판단 기준의 층위 혼동에 초점을 둔다.",
        "rule": "선지의 핵심어가 지문에서 같은 층위의 말인지, 더 높은/낮은 층위의 말인지 표시한다.",
    },
    "UNWARRANTED_ASSUMPTION_ADDED": {
        "ko": "무근거 가정 추가",
        "definition": "지문이나 조건이 허용하지 않은 전제, 배경 설명, 경로, 사례, 일반론을 덧붙여 선지를 살린 오류.",
        "positive": "가능한 배경 설명을 직접 보충하거나, 불명확한 작용 경로를 임의로 제한했을 때 사용한다.",
        "negative": "명시 조건을 잘못 적용한 경우에는 SCOPE_CONDITION_MISAPPLICATION을 우선한다.",
        "neighbors": "CHOICE_VERIFICATION_FAILURE는 검산 누락, UNWARRANTED_ASSUMPTION_ADDED는 추가 전제가 판단을 움직였을 때 쓴다.",
        "rule": "내가 덧붙인 문장이 지문에 있는지 표시하고, 없으면 선지 판단에서 제거한다.",
    },
    "GLOBAL_CONSTRAINT_DROPPED": {
        "ko": "전역 제약 누락",
        "definition": "국소 판단은 맞았지만 전체 표, 전역 규칙, 남은 자유도, 공통 제약, 세트 구조를 끝까지 유지하지 못한 오류.",
        "positive": "블록 형성 후 남은 원소를 확인하지 않거나, 상위 행·전체 입력공간·새 규칙을 재검산하지 않은 경우 사용한다.",
        "negative": "형식 조건 자체를 잘못 세운 경우에는 FORMAL_CONDITION_ERROR를 우선한다.",
        "neighbors": "TABLE_DIAGRAM_ENCODING_ERROR는 표 입력·부호화 실패, GLOBAL_CONSTRAINT_DROPPED는 입력 후 유지 실패다.",
        "rule": "국소 결론을 낸 뒤 남은 경우, 상위 조건, 반례 가능성을 별도 체크한다.",
    },
    "ARGUMENT_STRUCTURE_INCOMPLETE": {
        "ko": "논증 구조 미완성",
        "definition": "강화·약화, 반박, 귀류, 중간결론, 필요조건, 비교 논증 등 논증의 inferential 구조를 끝까지 완성하지 못한 오류.",
        "positive": "한 이론 약화가 다른 이론 강화인지, 결론 직전 노드가 무엇인지, 반박 대상이 기준인지 결론인지 놓친 경우 사용한다.",
        "negative": "논증 구조보다 계산식·조건식 조작이 핵심이면 FORMAL_CONDITION_ERROR를 우선한다.",
        "neighbors": "CONCEPT_LAYER_CONFUSION은 판단 층위, ARGUMENT_STRUCTURE_INCOMPLETE는 추론 연결 단계가 핵심이다.",
        "rule": "주장, 근거, 중간결론, 최종결론을 표시하고 선지가 어느 연결을 평가하는지 확인한다.",
    },
    "CHOICE_VERIFICATION_FAILURE": {
        "ko": "선지 검산 실패",
        "definition": "그럴듯한 선택지나 소거 결과를 지문·조건·정답 후보와 마지막으로 대조하지 못한 오류.",
        "positive": "답 후보를 잡은 뒤 선택지의 정확한 문구, 예외, 선택 번호, 도출 결론과의 대응을 확인하지 않은 경우 사용한다.",
        "negative": "검산 이전에 명확한 조건식이나 개념 구분을 잘못 세운 경우 해당 기제 태그를 우선한다.",
        "neighbors": "TIME_PRESSURE_OR_ATTENTION_LAPSE는 운영 상태가 1차 원인일 때만 primary로 둔다.",
        "rule": "최종 표시 전 선택지의 주어·술어·제한어를 지문 근거 하나와 대응시킨다.",
    },
    "FORMAL_CONDITION_ERROR": {
        "ko": "형식 조건 처리 오류",
        "definition": "논리, 양화, 부등식, 절댓값, 필요·충분, 순서, 계산식, 조건 분기 등 형식 조건을 잘못 세우거나 조작한 오류.",
        "positive": "절댓값을 합식으로 풀거나, 존재양화·기대수익·예산식·참거짓 조건을 잘못 처리한 경우 사용한다.",
        "negative": "계산 전 표의 행·열을 잘못 읽은 경우 TABLE_DIAGRAM_ENCODING_ERROR를 우선한다.",
        "neighbors": "SCOPE_CONDITION_MISAPPLICATION은 조건 범위, FORMAL_CONDITION_ERROR는 형식 조작 자체에 초점을 둔다.",
        "rule": "문장 판단 전에 식, 부등호, 양화사, 분기 조건을 먼저 외부화한다.",
    },
    "TABLE_DIAGRAM_ENCODING_ERROR": {
        "ko": "표·도식·변수 인코딩 오류",
        "definition": "표, 도식, 그래프, 실험 설계, 변수 비교, 수치 임계값, 기호 라벨을 선지 판단 전에 올바른 문장·식·비교쌍으로 재부호화하지 못한 오류.",
        "positive": "현재/선호 열, ㉠·㉡ 라벨, 투과율/반사율, 점수/등수, 평균/분포, 실험 비교 변수, 임계값을 잘못 인코딩했을 때 사용한다.",
        "negative": "입력값은 맞게 읽었지만 전체 제약을 끝까지 유지하지 못했다면 GLOBAL_CONSTRAINT_DROPPED를 우선한다.",
        "neighbors": "RELATION_DIRECTION_REVERSAL은 인코딩된 값의 방향만 뒤집힌 경우 secondary로 자주 붙는다. FORMAL_CONDITION_ERROR는 식 조작 자체가 핵심일 때 우선한다.",
        "rule": "표·그래프·실험 설계는 선지로 가기 전에 한 줄 식, 2x2 표, 또는 변수 비교쌍으로 다시 쓴다.",
    },
    "TIME_PRESSURE_OR_ATTENTION_LAPSE": {
        "ko": "시간 압박·주의 저하",
        "definition": "시간 압박, 피로, 후반부 집중력 저하, 소재 친숙성에 의한 경계심 저하가 1차 원인으로 확인되는 운영 오류.",
        "positive": "사용자 리뷰가 직접 시간·피로·대충 선택·글자 오독을 주요 원인으로 제시할 때 primary로 사용한다.",
        "negative": "운영 상태가 보조 설명일 뿐 명확한 기제 오류가 있으면 secondary로 둔다.",
        "neighbors": "CHOICE_VERIFICATION_FAILURE는 루틴 누락, TIME_PRESSURE_OR_ATTENTION_LAPSE는 그 루틴이 무너진 운영 원인이다.",
        "rule": "후반부·시간 부족 문항은 선택 전 제한어와 비교어만이라도 별도로 표시한다.",
    },
    "INSUFFICIENT_REVIEW_BASIS": {
        "ko": "리뷰 근거 부족",
        "definition": "정답·오답과 canonical 문항은 확인되지만 사용자 사고과정이나 피드백이 비어 있어 기제 태그를 확정하기 어려운 보류 태그.",
        "positive": "unreviewed 상태이거나 self-review와 assistant feedback이 모두 없어 오답 메커니즘을 재구성할 수 없을 때 사용한다.",
        "negative": "리뷰 근거가 조금이라도 있어 낮은 확신의 기제 진단이 가능한 경우에는 해당 기제 태그와 low confidence를 사용한다.",
        "neighbors": "needs_review=true와 함께 사용하며, final_error_tags로 승격하지 않는 임시 품질 태그다.",
        "rule": "canonical만으로 선택 이유를 추정하지 말고, 사용자 복기 또는 피드백 확보 후 다시 태깅한다.",
    },
}


ASSIGNMENTS: dict[str, Assignment] = {
    "data/reviews/2020 언어이해 홀수형/q03.review.json": Assignment("CHOICE_VERIFICATION_FAILURE", ("UNWARRANTED_ASSUMPTION_ADDED",), "high", "과목 인상으로 2번을 배제하고 5번을 지문 변화 사례와 끝까지 대조하지 못했다."),
    "data/reviews/2020 언어이해 홀수형/q05.review.json": Assignment("CONCEPT_LAYER_CONFUSION", ("TEXTUAL_REDEFINITION_MISSED",), "high", "제도상 지위 인정, 규범적 승인, 예법상 효과를 같은 층위로 묶었다."),
    "data/reviews/2020 언어이해 홀수형/q12.review.json": Assignment("CHOICE_VERIFICATION_FAILURE", ("CONCEPT_LAYER_CONFUSION",), "high", "양가성은 지나치게 엄격히 보면서 수용/거절의 행위 방향은 검산하지 않았다."),
    "data/reviews/2020 언어이해 홀수형/q16.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", ("TEXTUAL_REDEFINITION_MISSED",), "high", "조건부 가능성을 실현 단정으로 읽고 보편성을 중립성과 동일시했다."),
    "data/reviews/2020 언어이해 홀수형/q20.review.json": Assignment("ROLE_ATTRIBUTION_ERROR", ("CHOICE_VERIFICATION_FAILURE",), "high", "3차원주의 언어를 4차원주의자에게 귀속한 선지를 충분히 걸러내지 못했다."),
    "data/reviews/2020 추리논증 홀수형/q02.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", (), "high", "특별한 교육 수준 부정을 최소 학업성취 요구 부정으로 확장했다."),
    "data/reviews/2020 추리논증 홀수형/q06.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", (), "high", "형사절차상 불이익의 범위를 절차 형식으로 좁혀 입법형 처벌효과를 제외했다."),
    "data/reviews/2020 추리논증 홀수형/q08.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", (), "high", "사망 조건만 보고 명시적 반대 없음이라는 결합 단서를 생략했다."),
    "data/reviews/2020 추리논증 홀수형/q19.review.json": Assignment("GLOBAL_CONSTRAINT_DROPPED", ("ARGUMENT_STRUCTURE_INCOMPLETE",), "high", "복합조건의 후반 보상 조건을 끝까지 유지하지 못하고 강화/약화 효과를 분리하지 않았다."),
    "data/reviews/2020 추리논증 홀수형/q28.review.json": Assignment("TABLE_DIAGRAM_ENCODING_ERROR", ("RELATION_DIRECTION_REVERSAL",), "high", "현재 소유 열과 가장 선호하는 상품 열을 반대로 읽어 교환 방향이 뒤집혔다."),
    "data/reviews/2020 추리논증 홀수형/q29.review.json": Assignment("TABLE_DIAGRAM_ENCODING_ERROR", ("UNWARRANTED_ASSUMPTION_ADDED",), "high", "수령액수와 수령건수를 혼동하고 지문 내부 인과축을 현실 보험모형으로 보정했다."),
    "data/reviews/2020 추리논증 홀수형/q30.review.json": Assignment("ARGUMENT_STRUCTURE_INCOMPLETE", (), "medium", "보조금 경쟁에서 요금 경쟁으로 이어지는 정책 인과사슬을 끊어 읽은 것으로 재구성된다."),
    "data/reviews/2020 추리논증 홀수형/q31.review.json": Assignment("UNWARRANTED_ASSUMPTION_ADDED", (), "high", "명시되지 않은 B등급 조건을 잔여범주로 임의 보충했다."),
    "data/reviews/2020 추리논증 홀수형/q33.review.json": Assignment("FORMAL_CONDITION_ERROR", ("GLOBAL_CONSTRAINT_DROPPED",), "high", "블록을 만든 뒤 남은 원소의 상대순서 자유도를 검산하지 않았다."),
    "data/reviews/2020 추리논증 홀수형/q39.review.json": Assignment("TABLE_DIAGRAM_ENCODING_ERROR", ("TEXTUAL_REDEFINITION_MISSED", "RELATION_DIRECTION_REVERSAL"), "high", "양이온교환수지 명칭을 지문식 부호표로 재인코딩하지 못하고 양전하 수지로 읽었다."),
    "data/reviews/2020 추리논증 홀수형/q40.review.json": Assignment("FORMAL_CONDITION_ERROR", (), "high", "전위차 조건을 절댓값 차이식이 아니라 합식처럼 세웠다.", True, "원본 review JSON에 쉼표 누락이 있어 좁은 in-memory repair로 읽었다."),
    "data/reviews/2021 언어이해 홀수형/q01.review.json": Assignment("CHOICE_VERIFICATION_FAILURE", (), "medium", "선지의 정오 방향을 마지막에 재확인하지 못한 것으로 리뷰가 정리한다."),
    "data/reviews/2021 언어이해 홀수형/q03.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", (), "medium", "프로세스 마이닝 기능 적용 범위와 필요한 자료 여부를 분리하지 못했다."),
    "data/reviews/2021 언어이해 홀수형/q10.review.json": Assignment("UNWARRANTED_ASSUMPTION_ADDED", (), "medium", "일반 가능성을 특정 범죄·피해자·처벌 형식의 대응으로 연결했다."),
    "data/reviews/2021 언어이해 홀수형/q14.review.json": Assignment("CONCEPT_LAYER_CONFUSION", ("TIME_PRESSURE_OR_ATTENTION_LAPSE",), "medium", "통일성 등 대비축의 수식어가 바뀌는 순간을 별도 개념으로 처리하지 못했다."),
    "data/reviews/2021 언어이해 홀수형/q28.review.json": Assignment("ROLE_ATTRIBUTION_ERROR", ("SCOPE_CONDITION_MISAPPLICATION",), "medium", "입장 지시어와 술어가 자기 주장인지 상대 비판인지 분리하지 못했다."),
    "data/reviews/2021 언어이해 홀수형/q29.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", (), "medium", "약한 부정을 강한 부정처럼 읽고 표현 강도를 검증하지 못했다."),
    "data/reviews/2021 언어이해 홀수형/q30.review.json": Assignment("CONCEPT_LAYER_CONFUSION", (), "medium", "사례 결론보다 적용 입장의 판단 기준이 중요하다는 층위를 놓쳤다."),
    "data/reviews/2021 추리논증 홀수형/q01.review.json": Assignment("ARGUMENT_STRUCTURE_INCOMPLETE", (), "medium", "자료 방향과 강화/약화 평가어의 연결을 끝까지 대조하지 못했다."),
    "data/reviews/2021 추리논증 홀수형/q06.review.json": Assignment("RELATION_DIRECTION_REVERSAL", ("TABLE_DIAGRAM_ENCODING_ERROR",), "high", "㉠·㉡ 기호와 실제 금액 의미의 대응을 최종 선택 단계에서 뒤집었다."),
    "data/reviews/2021 추리논증 홀수형/q08.review.json": Assignment("GLOBAL_CONSTRAINT_DROPPED", ("FORMAL_CONDITION_ERROR",), "high", "규정 번호 순서라는 전역 산정 알고리즘을 사건 발생 순서로 대체했다."),
    "data/reviews/2021 추리논증 홀수형/q13.review.json": Assignment("GLOBAL_CONSTRAINT_DROPPED", (), "medium", "예방 조치가 실제 행위 발생 여부를 바꾼다는 전역 조건을 유지하지 못했다."),
    "data/reviews/2021 추리논증 홀수형/q21.review.json": Assignment("GLOBAL_CONSTRAINT_DROPPED", (), "medium", "가능 배치 하나를 찾은 뒤 대칭·교환 가능성을 끝까지 검산하지 않았다."),
    "data/reviews/2021 추리논증 홀수형/q22.review.json": Assignment("FORMAL_CONDITION_ERROR", (), "high", "존재양화사의 증인을 고정해 성질을 적용하는 처리를 놓쳤다."),
    "data/reviews/2021 추리논증 홀수형/q27.review.json": Assignment("RELATION_DIRECTION_REVERSAL", (), "high", "보상 계산에서 주는 사람과 받는 사람을 바꾸어 계산했다."),
    "data/reviews/2021 추리논증 홀수형/q30.review.json": Assignment("ARGUMENT_STRUCTURE_INCOMPLETE", (), "medium", "동태 과정에서 초기·중간·이후 단계와 변수 연결을 끝까지 분리하지 못했다."),
    "data/reviews/2021 추리논증 홀수형/q31.review.json": Assignment("GLOBAL_CONSTRAINT_DROPPED", ("CHOICE_VERIFICATION_FAILURE",), "medium", "뒤늦게 발견한 두 번째 규칙을 이미 살려 둔 선지 전체에 다시 적용하지 않았다."),
    "data/reviews/2021 추리논증 홀수형/q32.review.json": Assignment("FORMAL_CONDITION_ERROR", (), "high", "차이와 불평등 정도를 절댓값으로 처리하지 않았다."),
    "data/reviews/2021 추리논증 홀수형/q34.review.json": Assignment("FORMAL_CONDITION_ERROR", ("TABLE_DIAGRAM_ENCODING_ERROR",), "medium", "기대수익을 수익×확률로 외부화하지 않고 실험 차이를 계산하지 않았다."),
    "data/reviews/2021 추리논증 홀수형/q36.review.json": Assignment("GLOBAL_CONSTRAINT_DROPPED", ("RELATION_DIRECTION_REVERSAL",), "medium", "가설의 A/B 가능성을 둘 다 열어 두지 않고 한 출발지만 고려했다."),
    "data/reviews/2022 언어이해 홀수형/q19.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", ("CONCEPT_LAYER_CONFUSION",), "high", "공동체 이익이라는 궁극 지향을 회사법 내부 신인의무 확장 주장으로 옮겨 읽었다."),
    "data/reviews/2022 언어이해 홀수형/q29.review.json": Assignment("TEXTUAL_REDEFINITION_MISSED", ("CONCEPT_LAYER_CONFUSION",), "high", "복종/부합 등 지문 내부 대비쌍과 기술어 치환을 감지하지 못했다."),
    "data/reviews/2022 추리논증 짝수형/q06.review.json": Assignment("TEXTUAL_REDEFINITION_MISSED", ("SCOPE_CONDITION_MISAPPLICATION",), "high", "업무수탁자와 제3자의 정의상 지위 구분을 건너뛰고 목적 범위를 넓혔다."),
    "data/reviews/2022 추리논증 짝수형/q10.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", (), "high", "행위 객체, 유포 방식, 매체 요건, 행위자 차이를 분리하지 못했다."),
    "data/reviews/2022 추리논증 짝수형/q18.review.json": Assignment("CONCEPT_LAYER_CONFUSION", ("ARGUMENT_STRUCTURE_INCOMPLETE",), "high", "점수 상승과 등수 상승을 같은 결과로 보고 필요조건 선지의 강도를 과하게 인정했다."),
    "data/reviews/2022 추리논증 짝수형/q24.review.json": Assignment("TABLE_DIAGRAM_ENCODING_ERROR", ("CONCEPT_LAYER_CONFUSION",), "high", "주관/객관과 내재/외재의 2x2 기준을 표로 고정하지 않아 개수 판단이 흔들렸다."),
    "data/reviews/2022 추리논증 짝수형/q25.review.json": Assignment("CONCEPT_LAYER_CONFUSION", (), "high", "결과 개선과 상대방을 합리적 주체로 존중한다는 정당화 방식을 혼동했다."),
    "data/reviews/2022 추리논증 짝수형/q26.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", ("FORMAL_CONDITION_ERROR",), "high", "0 또는 양수라는 경계값 포함 조건에서 0을 제외했다."),
    "data/reviews/2022 추리논증 짝수형/q27.review.json": Assignment("TABLE_DIAGRAM_ENCODING_ERROR", (), "high", "실험에서 고정된 변수와 조작된 변수를 분리하지 못했다."),
    "data/reviews/2022 추리논증 짝수형/q28.review.json": Assignment("TABLE_DIAGRAM_ENCODING_ERROR", ("RELATION_DIRECTION_REVERSAL",), "high", "지수 부호의 현실 의미를 고정하지 않아 혜택 확산과 범죄 전이를 뒤집었다."),
    "data/reviews/2022 추리논증 짝수형/q33.review.json": Assignment("FORMAL_CONDITION_ERROR", ("TIME_PRESSURE_OR_ATTENTION_LAPSE",), "high", "범위형 조건에서 극단값과 반례를 끝까지 찾지 않았다."),
    "data/reviews/2022 추리논증 짝수형/q34.review.json": Assignment("FORMAL_CONDITION_ERROR", (), "high", "각 진술자의 두 문장 중 하나만 참이라는 강한 제약을 이용해 경우를 줄이지 못했다."),
    "data/reviews/2022 추리논증 짝수형/q36.review.json": Assignment("ARGUMENT_STRUCTURE_INCOMPLETE", (), "high", "설명 연결문과 최종 결론을 지지하는 배경근거의 역할을 분리하지 못했다."),
    "data/reviews/2022 추리논증 짝수형/q38.review.json": Assignment("UNWARRANTED_ASSUMPTION_ADDED", (), "high", "특정 장내 세균의 작용 경로를 TH17로만 임의 제한했다."),
    "data/reviews/2022 추리논증 짝수형/q39.review.json": Assignment("ARGUMENT_STRUCTURE_INCOMPLETE", ("CONCEPT_LAYER_CONFUSION",), "high", "혈당 개선이라는 결과변수만 보고 십이지장 우회라는 조작변수와 가설 연결을 놓쳤다."),
    "data/reviews/2023 언어이해 짝수형/q12.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", (), "high", "환원하지 않는다는 말을 주요하지 않게 본다는 뜻으로 축소하고 연속성/발생 강도를 분리하지 못했다."),
    "data/reviews/2023 언어이해 짝수형/q19.review.json": Assignment("GLOBAL_CONSTRAINT_DROPPED", ("SCOPE_CONDITION_MISAPPLICATION",), "high", "사회 특성과 문제 특수성이라는 이중 조건 중 한 축만 전체 결정 기준으로 승격했다."),
    "data/reviews/2023 언어이해 짝수형/q22.review.json": Assignment("CONCEPT_LAYER_CONFUSION", (), "high", "낭만주의/낭만적인 것의 구별을 단계적 추상화 관계가 아니라 단절 관계로 읽었다."),
    "data/reviews/2023 언어이해 짝수형/q23.review.json": Assignment("CONCEPT_LAYER_CONFUSION", (), "high", "정당한 추상화 압축과 지문 밖 상상력 개념 투입을 구별하지 못했다."),
    "data/reviews/2023 언어이해 짝수형/q26.review.json": Assignment("TIME_PRESSURE_OR_ATTENTION_LAPSE", ("CHOICE_VERIFICATION_FAILURE",), "high", "후반부 피로와 소재 친숙성으로 ㄱ·ㄴ·ㄷ 지문 근거 검증 루틴이 무너졌다."),
    "data/reviews/2023 언어이해 짝수형/q27.review.json": Assignment("RELATION_DIRECTION_REVERSAL", ("TIME_PRESSURE_OR_ATTENTION_LAPSE",), "high", "투과율을 반사율로 읽어 직전 문항의 개념어가 다음 조건어를 덮었다."),
    "data/reviews/2023 추리논증 짝수형/q04.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", (), "high", "소송 제기 가능성과 그 사유로 제기 가능성을 구분하지 않았다."),
    "data/reviews/2023 추리논증 짝수형/q10.review.json": Assignment("TABLE_DIAGRAM_ENCODING_ERROR", ("FORMAL_CONDITION_ERROR",), "high", "누적 수량 비교의 임계값을 1,000주 낮게 잡았다."),
    "data/reviews/2023 추리논증 짝수형/q19.review.json": Assignment("ARGUMENT_STRUCTURE_INCOMPLETE", (), "medium", "도식형 논증에서 후반 중간결론과 최종결론 직전 연결을 끝까지 대조하지 못했다."),
    "data/reviews/2023 추리논증 짝수형/q21.review.json": Assignment("ARGUMENT_STRUCTURE_INCOMPLETE", ("UNWARRANTED_ASSUMPTION_ADDED",), "high", "강화/약화에서 주장 대상의 방향을 좁게 잡고 자신의 구분을 선지에 보충했다."),
    "data/reviews/2023 추리논증 짝수형/q28.review.json": Assignment("CONCEPT_LAYER_CONFUSION", ("TABLE_DIAGRAM_ENCODING_ERROR",), "high", "현상 발생과 COVID 원인에 의한 발생, 평균과 하위집단 분포를 혼동했다."),
    "data/reviews/2023 추리논증 짝수형/q33.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", (), "high", "많아야 1명이라는 상한 조건을 정확히 1명이라는 등식 조건으로 고정했다."),
    "data/reviews/2025 언어이해 짝수형/q06.review.json": Assignment("CHOICE_VERIFICATION_FAILURE", ("TABLE_DIAGRAM_ENCODING_ERROR",), "medium", "도출한 효소/기질 결론과 실제 선택지가 대응하는지 최종 확인하지 않았다."),
    "data/reviews/2025 언어이해 짝수형/q13.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", (), "high", "용인·인정의 조건부 표현을 지문 문맥보다 강하게 해석했다."),
    "data/reviews/2025 언어이해 짝수형/q14.review.json": Assignment("CHOICE_VERIFICATION_FAILURE", ("TIME_PRESSURE_OR_ATTENTION_LAPSE",), "medium", "어려운 정답 선지에 자원이 묶여 명백히 충돌하는 선택 선지를 재검증하지 못했다."),
    "data/reviews/2025 언어이해 짝수형/q20.review.json": Assignment("CHOICE_VERIFICATION_FAILURE", (), "medium", "소거 말미에 지문 조건 충족 검증 대신 상대적으로 덜 틀려 보이는 선지를 골랐다."),
    "data/reviews/2025 언어이해 짝수형/q21.review.json": Assignment("CHOICE_VERIFICATION_FAILURE", (), "low", "독립적 사고과정이 충분히 복원되지 않아 같은 지문 세트의 기준 이동 가설로만 남는다.", True, "사용자의 독립 리뷰 근거가 부족해 세트 연쇄 오류 가설만 가능하다."),
    "data/reviews/2025 언어이해 짝수형/q26.review.json": Assignment("CHOICE_VERIFICATION_FAILURE", (), "high", "배제형 문항에서 지문 정보 부족보다 지문 핵심과 직접 충돌하는 선지를 우선하지 못했다."),
    "data/reviews/2025 추리논증 짝수형/q09.review.json": Assignment("INSUFFICIENT_REVIEW_BASIS", (), "low", "review 상태가 unreviewed이며 사고과정과 피드백이 비어 있다.", True, "사용자 self-review와 assistant feedback이 없어 canonical만으로 기제를 확정할 수 없다."),
    "data/reviews/2025 추리논증 짝수형/q23.review.json": Assignment("INSUFFICIENT_REVIEW_BASIS", (), "low", "review 상태가 unreviewed이며 사고과정과 피드백이 비어 있다.", True, "사용자 self-review와 assistant feedback이 없어 canonical만으로 기제를 확정할 수 없다."),
    "data/reviews/2025 추리논증 짝수형/q29.review.json": Assignment("INSUFFICIENT_REVIEW_BASIS", (), "low", "review 상태가 unreviewed이며 사고과정과 피드백이 비어 있다.", True, "사용자 self-review와 assistant feedback이 없어 canonical만으로 기제를 확정할 수 없다."),
    "data/reviews/2025 추리논증 짝수형/q33.review.json": Assignment("INSUFFICIENT_REVIEW_BASIS", (), "low", "review 상태가 unreviewed이며 사고과정과 피드백이 비어 있다.", True, "사용자 self-review와 assistant feedback이 없어 canonical만으로 기제를 확정할 수 없다."),
    "data/reviews/2025 추리논증 짝수형/q34.review.json": Assignment("INSUFFICIENT_REVIEW_BASIS", (), "low", "review 상태가 unreviewed이며 사고과정과 피드백이 비어 있다.", True, "사용자 self-review와 assistant feedback이 없어 canonical만으로 기제를 확정할 수 없다."),
    "data/reviews/2026 언어이해 홀수형/q06.review.json": Assignment("GLOBAL_CONSTRAINT_DROPPED", (), "high", "지역 행의 완결성이 아니라 전체 의사결정표의 입력공간 처리 여부를 봐야 했다."),
    "data/reviews/2026 언어이해 홀수형/q10.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", (), "high", "노비 제외라는 예외 조건 누락을 허용 가능한 축약으로 처리했다."),
    "data/reviews/2026 언어이해 홀수형/q12.review.json": Assignment("TEXTUAL_REDEFINITION_MISSED", ("RELATION_DIRECTION_REVERSAL",), "high", "제도 변화의 방식어인 보완·도입을 대체로 읽어 지문식 변화 구조를 바꾸었다."),
    "data/reviews/2026 언어이해 홀수형/q15.review.json": Assignment("CONCEPT_LAYER_CONFUSION", ("ARGUMENT_STRUCTURE_INCOMPLETE",), "high", "인식 불가능성을 정보 부족이 아니라 개념상 성립 불가능을 보이는 귀류로 완성하지 못했다."),
    "data/reviews/2026 언어이해 홀수형/q17.review.json": Assignment("CONCEPT_LAYER_CONFUSION", ("UNWARRANTED_ASSUMPTION_ADDED",), "high", "정책·제도·기술·환경이라는 원인 범주를 같은 설명 경로로 묶고 배경 설명을 보충했다."),
    "data/reviews/2026 언어이해 홀수형/q21.review.json": Assignment("CONCEPT_LAYER_CONFUSION", ("ROLE_ATTRIBUTION_ERROR",), "high", "상대화되는 서구적 보편성과 탐색되는 인간적 보편성의 위치를 뒤집었다."),
    "data/reviews/2026 언어이해 홀수형/q26.review.json": Assignment("TIME_PRESSURE_OR_ATTENTION_LAPSE", ("CHOICE_VERIFICATION_FAILURE",), "high", "시간 압박 속에서 '와 달리' 같은 비교 구조를 재확인하지 못했다."),
    "data/reviews/2026 추리논증 홀수형/q01.review.json": Assignment("ROLE_ATTRIBUTION_ERROR", ("SCOPE_CONDITION_MISAPPLICATION",), "high", "통제 목표 대상과 법 규범이 직접 작용하는 상대방을 분리하지 못했다."),
    "data/reviews/2026 추리논증 홀수형/q03.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", (), "high", "허가증 가격이 낮을 가능성을 형평성 우위가 보장된다는 결론으로 바꾸었다."),
    "data/reviews/2026 추리논증 홀수형/q04.review.json": Assignment("ARGUMENT_STRUCTURE_INCOMPLETE", ("TEXTUAL_REDEFINITION_MISSED",), "high", "올림픽 수준의 대회에서 달성된 기록을 올림픽 수준의 기록으로 바꾸고 반박 대상을 좁혔다."),
    "data/reviews/2026 추리논증 홀수형/q05.review.json": Assignment("CONCEPT_LAYER_CONFUSION", (), "high", "현재 제도의 공통 한계를 제안된 조건부 불구속의 법적 성격 판단으로 바꾸었다."),
    "data/reviews/2026 추리논증 홀수형/q08.review.json": Assignment("ROLE_ATTRIBUTION_ERROR", ("UNWARRANTED_ASSUMPTION_ADDED",), "high", "C의 우수 인력 요소를 A에게도 붙여 공통점을 과잉 일반화했다."),
    "data/reviews/2026 추리논증 홀수형/q21.review.json": Assignment("FORMAL_CONDITION_ERROR", (), "high", "0.91, 0.92, 0.92 이상처럼 가까운 수치 비교를 외부화하지 않았다."),
    "data/reviews/2026 추리논증 홀수형/q24.review.json": Assignment("SCOPE_CONDITION_MISAPPLICATION", ("TEXTUAL_REDEFINITION_MISSED",), "medium", "정책 시행 시 편익·비용 구조와 비개입 현상 자체를 구분하지 못했다."),
    "data/reviews/2026 추리논증 홀수형/q26.review.json": Assignment("FORMAL_CONDITION_ERROR", (), "high", "새 가격에서 비교해야 할 가격(X) <= 가격(Y) 관계 대신 초기 기준값 120과 비교했다."),
    "data/reviews/2026 추리논증 홀수형/q29.review.json": Assignment("ARGUMENT_STRUCTURE_INCOMPLETE", ("UNWARRANTED_ASSUMPTION_ADDED",), "high", "A 이론 약화가 B 이론 강화를 자동으로 뜻하는지 별도 검증하지 않고 두 이론의 상호배타성을 보충했다."),
}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def compact(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def read_review(path: Path) -> tuple[dict[str, Any], str | None]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        repaired = re.sub(
            r'("provisional_error_tags"\s*:\s*\[\]\s*)\n(\s*"correction_rule")',
            r"\1,\n\2",
            text,
            count=1,
        )
        return json.loads(repaired), f"narrow in-memory JSON repair: {exc}"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_canonical() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    questions: dict[str, dict[str, Any]] = {}
    passages: dict[str, dict[str, Any]] = {}
    for directory in sorted(CANONICAL_DIR.iterdir()):
        if not directory.is_dir():
            continue
        for question in load_jsonl(directory / "questions.jsonl"):
            questions[question["id"]] = question
        for passage in load_jsonl(directory / "passages.jsonl"):
            passages[passage["id"]] = passage
    return questions, passages


def infer_year(exam_id: str, review_path: str) -> int | None:
    match = re.search(r"(20\d{2})", exam_id) or re.search(r"(20\d{2})", review_path)
    return int(match.group(1)) if match else None


def infer_section(exam_id: str, review_path: str) -> str:
    text = f"{exam_id} {review_path}"
    if "언어" in text or "verbal" in text:
        return "언어이해"
    if "추리" in text or "reasoning" in text:
        return "추리논증"
    return "unknown"


def infer_question_type(stem: str) -> str:
    if "일치" in stem:
        return "content agreement"
    if "추론" in stem:
        return "inference"
    if "평가" in stem or "강화" in stem or "약화" in stem:
        return "argument evaluation"
    if "규정" in stem or "사례" in stem or "적용" in stem:
        return "rule/application"
    if "분석" in stem or "구조" in stem:
        return "structure analysis"
    if "옳은 것만" in stem or "있는 대로" in stem:
        return "condition selection"
    return "reading/application"


def infer_domain(section: str, stem: str, passage: dict[str, Any] | None) -> str | None:
    text = f"{stem} {passage.get('body_text', '') if passage else ''}"
    checks = [
        ("법/규정", ("규정", "법", "소송", "형벌", "법원", "입법", "권리")),
        ("철학/윤리", ("철학", "윤리", "칸트", "헤겔", "공리주의", "자의식", "믿음")),
        ("경제/정책", ("경제", "정책", "시장", "보험", "가격", "성과급", "분담금")),
        ("과학/기술", ("실험", "단백질", "중력파", "전지", "세포", "효소", "혈당", "로봇")),
        ("논리/형식추론", ("참", "거짓", "조건", "가능세계", "명제", "배치", "순서")),
        ("문학/비평", ("작품", "계봉", "문학", "보편성")),
        ("사회/역사", ("역사", "사회", "민주주의", "식민지", "제도")),
    ]
    for label, needles in checks:
        if any(needle in text for needle in needles):
            return label
    return f"{section} 일반"


def build_record(
    review_path: Path,
    review: dict[str, Any],
    parse_note: str | None,
    question: dict[str, Any] | None,
    passage: dict[str, Any] | None,
    assignment: Assignment,
) -> dict[str, Any]:
    review_rel = rel(review_path)
    holdout = review_rel in HOLDOUT_RECORDS
    grading = review.get("grading") or {}
    selected = grading.get("selected_choice")
    correct = grading.get("correct_choice")
    choices = question.get("choices", []) if question else []
    selected_choice = next((choice for choice in choices if choice.get("choice_no") == selected), None)
    correct_choice = next((choice for choice in choices if choice.get("choice_no") == correct), None)
    stem = question.get("stem", "") if question else ""
    section = infer_section(review.get("exam_id", ""), review_rel)
    question_type = infer_question_type(stem)
    self_review = review.get("user_self_review") or {}
    assistant_feedback = review.get("assistant_feedback") or {}

    needs_review_reason = assignment.needs_review_reason
    if parse_note:
        needs_review_reason = (
            f"{needs_review_reason} {parse_note}" if needs_review_reason else parse_note
        )

    if question is None:
        canonical_question_summary = "Canonical question was not found."
        selected_issue = "Cannot compare selected choice because canonical question data is missing."
        correct_basis = "Cannot verify correct choice because canonical question data is missing."
        key_pointer = "missing canonical question"
    else:
        canonical_question_summary = f"{question_type}: {compact(stem, 100)}"
        if assignment.primary == "INSUFFICIENT_REVIEW_BASIS":
            selected_issue = (
                f"Choice {selected} is recorded as incorrect, but no review rationale is present "
                "to reconstruct why it was attractive."
            )
        else:
            selected_issue = (
                f"Choice {selected} is the selected incorrect option; review evidence indicates "
                f"{assignment.note}"
            )
        correct_basis = (
            f"Canonical answer key marks choice {correct} as correct"
            + (f"; choice text begins: {compact(correct_choice.get('text'), 70)}" if correct_choice else ".")
        )
        passage_part = (
            f"passage {question.get('passage_id')} range {passage.get('question_range')}"
            if passage
            else "no linked passage"
        )
        key_pointer = (
            f"{question.get('id')}; {passage_part}; selected choice {selected}; correct choice {correct}"
        )

    structure_notes = (
        f"{question_type}; {len(choices)} choices; "
        + (
            f"linked passage range {passage.get('question_range')}"
            if passage
            else "no passage linkage"
        )
    )

    record = {
        "review_file": review_rel,
        "exam_id": review.get("attempt_id") or review.get("exam_id"),
        "year": infer_year(review.get("exam_id", ""), review_rel),
        "section": section,
        "question_no": review.get("question_no"),
        "question_id": review.get("question_id"),
        "selected_choice": selected,
        "correct_choice": correct,
        "is_correct": grading.get("is_correct"),
        "problem_metadata": {
            "question_type": question_type,
            "domain_or_topic": infer_domain(section, stem, passage),
            "requires_passage": bool(question and question.get("passage_id")),
            "structure_notes": structure_notes,
        },
        "provisional_tags": {
            "primary": assignment.primary,
            "secondary": list(assignment.secondary),
            "confidence": assignment.confidence,
        },
        "tag_rationale": (
            f"Provisional tag is based on the review diagnosis plus canonical structure. "
            f"The canonical item is a {question_type} question with selected choice {selected} "
            f"and correct choice {correct}; the review-specific mechanism is: {assignment.note}"
        ),
        "canonical_basis": {
            "question_summary": canonical_question_summary,
            "selected_choice_issue": selected_issue,
            "correct_choice_basis": correct_basis,
            "key_evidence_pointer": key_pointer,
        },
        "review_basis": {
            "user_self_diagnosis_summary": compact(
                self_review.get("reasoning_text") or self_review.get("current_reflection"),
                170,
            )
            or "No user self-review text is present.",
            "assistant_feedback_summary": compact(
                assistant_feedback.get("diagnosis_text")
                or assistant_feedback.get("correction_rule"),
                190,
            )
            or "No assistant feedback is present.",
        },
        "needs_review": bool(assignment.needs_review or parse_note),
        "needs_review_reason": needs_review_reason,
        "holdout": holdout,
        "holdout_reason": HOLDOUT_REASON if holdout else None,
        "use_for_tag_frequency": not holdout,
        "use_for_final_tag_promotion": not holdout,
        "revisit_plan": HOLDOUT_REVISIT_PLAN if holdout else None,
    }

    return record


def markdown_table(rows: list[list[Any]]) -> str:
    header = rows[0]
    body = rows[1:]
    lines = [
        "| " + " | ".join(str(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def write_dictionary(records: list[dict[str, Any]]) -> None:
    reps: dict[str, list[str]] = defaultdict(list)
    for record in records:
        tag = record["provisional_tags"]["primary"]
        if len(reps[tag]) < 4:
            label = record["review_file"]
            if record["holdout"]:
                label = f"{label} (holdout)"
            reps[tag].append(label)

    lines = [
        "# Provisional Tag Dictionary",
        "",
        "These tags are provisional mechanism labels for review and later promotion. They are not final tags.",
        "",
    ]
    for tag_id in sorted(TAG_DEFS):
        tag = TAG_DEFS[tag_id]
        lines.extend(
            [
                f"## `{tag_id}`",
                "",
                f"- Korean display name: {tag['ko']}",
                f"- Definition: {tag['definition']}",
                f"- Positive criteria: {tag['positive']}",
                f"- Negative criteria: {tag['negative']}",
                f"- Neighboring tags: {tag['neighbors']}",
                f"- Representative review files: {', '.join(reps.get(tag_id, ['none in this corpus']))}",
                f"- Suggested correction rule: {tag['rule']}",
                "",
            ]
        )
    (OUT_DIR / "tag_dictionary.provisional.md").write_text("\n".join(lines), encoding="utf-8")


def write_summary(records: list[dict[str, Any]], review_count: int, parse_notes: list[str]) -> None:
    active_records = [record for record in records if record["use_for_tag_frequency"]]
    holdout_records = [record for record in records if record["holdout"]]
    needs_review_non_holdout = [
        record for record in records if record["needs_review"] and not record["holdout"]
    ]
    holdout_needs_review = [record for record in holdout_records if record["needs_review"]]

    primary_counts = Counter(record["provisional_tags"]["primary"] for record in active_records)
    all_counts = Counter()
    for record in active_records:
        all_counts[record["provisional_tags"]["primary"]] += 1
        all_counts.update(record["provisional_tags"]["secondary"])

    low_conf = [
        record
        for record in active_records
        if record["provisional_tags"]["confidence"] == "low"
    ]
    high_recurring = [
        (tag, count)
        for tag, count in primary_counts.most_common()
        if count >= 5 and tag != "INSUFFICIENT_REVIEW_BASIS"
    ]
    freq_rows = [["Tag", "Primary count", "Primary+secondary count"]]
    for tag, count in primary_counts.most_common():
        freq_rows.append([f"`{tag}`", count, all_counts[tag]])

    needs_rows = [["Review file", "Reason"]]
    for record in needs_review_non_holdout:
        needs_rows.append([record["review_file"], record["needs_review_reason"]])

    holdout_rows = [["Review file", "Reason", "Revisit plan"]]
    for record in holdout_records:
        holdout_rows.append(
            [record["review_file"], record["holdout_reason"], record["revisit_plan"]]
        )

    lines = [
        "# Provisional Tagging Audit Summary",
        "",
        "## Corpus Counts",
        "",
        f"- Review files inspected: {review_count}",
        f"- Wrong-answer records written: {len(records)}",
        f"- Active records used for tag analysis: {len(active_records)}",
        f"- Holdout records excluded from tag analysis: {len(holdout_records)}",
        f"- Needs-review records excluding holdouts: {len(needs_review_non_holdout)}",
        f"- Holdout records requiring later re-solve: {len(holdout_needs_review)}",
        "- Records with missing canonical data: 0",
        f"- Source JSON parse repairs used without modifying originals: {len(parse_notes)}",
        "",
        "Holdout records remain visible in `provisional_tags.jsonl`, but they are not active evidence for the provisional taxonomy and are excluded from tag frequency and final-promotion analysis.",
        "",
        "## Active Tag Frequency Table",
        "",
        markdown_table(freq_rows),
        "",
        "## High-Confidence Recurring Tags",
        "",
    ]
    if high_recurring:
        lines.extend(f"- `{tag}`: {count} primary records" for tag, count in high_recurring)
    else:
        lines.append("- None reached the recurrence threshold.")
    lines.extend(
        [
            "",
            "## Low-Confidence Or Unstable Tags",
            "",
            f"- Active low-confidence records: {len(low_conf)}",
            "- Holdout records are excluded from this count and from final tag promotion.",
            "- `INSUFFICIENT_REVIEW_BASIS` is a temporary data-quality tag and should not be promoted as a final error mechanism.",
            "- `CHOICE_VERIFICATION_FAILURE` should be reviewed carefully because it can become a secondary tag once a deeper mechanism is documented.",
            "",
            "## Needs Review Records Excluding Holdouts",
            "",
            markdown_table(needs_rows) if len(needs_rows) > 1 else "- None.",
            "",
            "## Holdout Records",
            "",
            markdown_table(holdout_rows) if len(holdout_rows) > 1 else "- None.",
            "",
            "## Recommended Merge/Split Candidates",
            "",
            "- Keep `SCOPE_CONDITION_MISAPPLICATION` separate from `GLOBAL_CONSTRAINT_DROPPED`: the former is about the scope of a condition, the latter about maintaining already-known global constraints.",
            "- Consider splitting `TABLE_DIAGRAM_ENCODING_ERROR` later if quantity/unit mistakes become frequent enough to justify a dedicated quantitative-unit tag.",
            "- Do not promote `INSUFFICIENT_REVIEW_BASIS`; current instances are holdouts and must be replaced after re-solving and review.",
            "- Keep `TIME_PRESSURE_OR_ATTENTION_LAPSE` as primary only when the review itself identifies fatigue, time pressure, or direct input lapse as the main cause.",
            "",
            "## Next Steps",
            "",
            "1. Re-solve the holdout records, then add user self-review and assistant feedback before assigning mechanism tags.",
            "2. Sample high-frequency tags against the original canonical question and passage records to confirm consistency.",
            "3. Promote only stable mechanism tags from active records into `final_error_tags`; leave operational, insufficient-basis, and holdout tags out of final labels unless explicitly approved.",
            "4. After promotion rules are settled, update the original review files in a separate, reviewed pass.",
            "",
        ]
    )
    (OUT_DIR / "tagging_audit_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    questions, passages = load_canonical()
    review_paths = sorted(REVIEWS_DIR.glob("*/*.review.json"))
    seen_paths = {rel(path) for path in review_paths}
    missing_assignments = sorted(seen_paths - set(ASSIGNMENTS))
    stale_assignments = sorted(set(ASSIGNMENTS) - seen_paths)
    if missing_assignments or stale_assignments:
        raise SystemExit(
            "Assignment mismatch:\n"
            f"missing={missing_assignments}\n"
            f"stale={stale_assignments}"
        )

    records: list[dict[str, Any]] = []
    parse_notes: list[str] = []
    for path in review_paths:
        review, parse_note = read_review(path)
        if parse_note:
            parse_notes.append(f"{rel(path)}: {parse_note}")
        if review.get("grading", {}).get("is_correct") is True:
            continue
        question = questions.get(review.get("question_id"))
        passage = passages.get(question.get("passage_id")) if question and question.get("passage_id") else None
        if question is None:
            raise SystemExit(f"Missing canonical question for {rel(path)}")
        if question.get("passage_id") and passage is None:
            raise SystemExit(f"Missing canonical passage for {rel(path)} -> {question.get('passage_id')}")
        records.append(
            build_record(
                path,
                review,
                parse_note,
                question,
                passage,
                ASSIGNMENTS[rel(path)],
            )
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "provisional_tags.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n")

    write_dictionary(records)
    write_summary(records, len(review_paths), parse_notes)
    active_records = [record for record in records if record["use_for_tag_frequency"]]
    holdout_records = [record for record in records if record["holdout"]]
    print(
        json.dumps(
            {
                "review_files": len(review_paths),
                "records_written": len(records),
                "output_dir": rel(OUT_DIR),
                "needs_review": sum(1 for record in records if record["needs_review"]),
                "needs_review_excluding_holdouts": sum(
                    1 for record in records if record["needs_review"] and not record["holdout"]
                ),
                "active_records_used_for_tag_analysis": len(active_records),
                "holdout_records": len(holdout_records),
                "parse_repairs": parse_notes,
                "primary_counts": Counter(
                    record["provisional_tags"]["primary"] for record in active_records
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
