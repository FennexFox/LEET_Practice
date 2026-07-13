# Provisional Tag Dictionary

These tags are provisional mechanism labels for review and later promotion. They are not final tags.

## `ARGUMENT_STRUCTURE_INCOMPLETE`

- Korean display name: 논증 구조 미완성
- Definition: 강화·약화, 반박, 귀류, 중간결론, 필요조건, 비교 논증 등 논증의 inferential 구조를 끝까지 완성하지 못한 오류.
- Positive criteria: 한 이론 약화가 다른 이론 강화인지, 결론 직전 노드가 무엇인지, 반박 대상이 기준인지 결론인지 놓친 경우 사용한다.
- Negative criteria: 논증 구조보다 계산식·조건식 조작이 핵심이면 FORMAL_CONDITION_ERROR를 우선한다.
- Neighboring tags: CONCEPT_LAYER_CONFUSION은 판단 층위, ARGUMENT_STRUCTURE_INCOMPLETE는 추론 연결 단계가 핵심이다.
- Representative review files: data/reviews/2020 추리논증 홀수형/q30.review.json, data/reviews/2021 추리논증 홀수형/q01.review.json, data/reviews/2021 추리논증 홀수형/q30.review.json, data/reviews/2022 추리논증 짝수형/q36.review.json
- Suggested correction rule: 주장, 근거, 중간결론, 최종결론을 표시하고 선지가 어느 연결을 평가하는지 확인한다.

## `CHOICE_VERIFICATION_FAILURE`

- Korean display name: 선지 검산 실패
- Definition: 그럴듯한 선택지나 소거 결과를 지문·조건·정답 후보와 마지막으로 대조하지 못한 오류.
- Positive criteria: 답 후보를 잡은 뒤 선택지의 정확한 문구, 예외, 선택 번호, 도출 결론과의 대응을 확인하지 않은 경우 사용한다.
- Negative criteria: 검산 이전에 명확한 조건식이나 개념 구분을 잘못 세운 경우 해당 기제 태그를 우선한다.
- Neighboring tags: TIME_PRESSURE_OR_ATTENTION_LAPSE는 운영 상태가 1차 원인일 때만 primary로 둔다.
- Representative review files: data/reviews/2021 언어이해 홀수형/q01.review.json, data/reviews/2025 언어이해 짝수형/q14.review.json, data/reviews/2025 언어이해 짝수형/q20.review.json, data/reviews/2025 언어이해 짝수형/q21.review.json
- Suggested correction rule: 최종 표시 전 선택지의 주어·술어·제한어를 지문 근거 하나와 대응시킨다.

## `CONCEPT_LAYER_CONFUSION`

- Korean display name: 개념 층위 혼동
- Definition: 대상과 표상, 결과와 정당화, 내용 관련 이유와 태도 관련 이유, 구체 사례와 추상 원리처럼 층위가 다른 개념을 섞은 오류.
- Positive criteria: 좋은 결과와 관점의 정당화 방식, 현상 발생과 특정 원인, 상상력과 개념적 사유처럼 층위 전환이 핵심일 때 사용한다.
- Negative criteria: 층위보다 단순 귀속 대상이 문제이면 ROLE_ATTRIBUTION_ERROR를 우선한다.
- Neighboring tags: ARGUMENT_STRUCTURE_INCOMPLETE는 논증 단계 누락, CONCEPT_LAYER_CONFUSION은 판단 기준의 층위 혼동에 초점을 둔다.
- Representative review files: data/reviews/2019 추리논증 홀수형/q22.review.json, data/reviews/2020 언어이해 홀수형/q05.review.json, data/reviews/2020 언어이해 홀수형/q12.review.json, data/reviews/2021 언어이해 홀수형/q14.review.json
- Suggested correction rule: 선지의 핵심어가 지문에서 같은 층위의 말인지, 더 높은/낮은 층위의 말인지 표시한다.

## `FORMAL_CONDITION_ERROR`

- Korean display name: 형식 조건 처리 오류
- Definition: 논리, 양화, 부등식, 절댓값, 필요·충분, 순서, 계산식, 조건 분기 등 형식 조건을 잘못 세우거나 조작한 오류.
- Positive criteria: 절댓값을 합식으로 풀거나, 존재양화·기대수익·예산식·참거짓 조건을 잘못 처리한 경우 사용한다.
- Negative criteria: 계산 전 표의 행·열을 잘못 읽은 경우 TABLE_DIAGRAM_ENCODING_ERROR를 우선한다.
- Neighboring tags: SCOPE_CONDITION_MISAPPLICATION은 조건 범위, FORMAL_CONDITION_ERROR는 형식 조작 자체에 초점을 둔다.
- Representative review files: data/reviews/2020 추리논증 홀수형/q33.review.json, data/reviews/2020 추리논증 홀수형/q40.review.json, data/reviews/2021 추리논증 홀수형/q22.review.json, data/reviews/2021 추리논증 홀수형/q32.review.json
- Suggested correction rule: 문장 판단 전에 식, 부등호, 양화사, 분기 조건을 먼저 외부화한다.

## `GLOBAL_CONSTRAINT_DROPPED`

- Korean display name: 전역 제약 누락
- Definition: 국소 판단은 맞았지만 전체 표, 전역 규칙, 남은 자유도, 공통 제약, 세트 구조를 끝까지 유지하지 못한 오류.
- Positive criteria: 블록 형성 후 남은 원소를 확인하지 않거나, 상위 행·전체 입력공간·새 규칙을 재검산하지 않은 경우 사용한다.
- Negative criteria: 형식 조건 자체를 잘못 세운 경우에는 FORMAL_CONDITION_ERROR를 우선한다.
- Neighboring tags: TABLE_DIAGRAM_ENCODING_ERROR는 표 입력·부호화 실패, GLOBAL_CONSTRAINT_DROPPED는 입력 후 유지 실패다.
- Representative review files: data/reviews/2020 추리논증 홀수형/q19.review.json, data/reviews/2021 추리논증 홀수형/q08.review.json, data/reviews/2021 추리논증 홀수형/q13.review.json, data/reviews/2021 추리논증 홀수형/q21.review.json
- Suggested correction rule: 국소 결론을 낸 뒤 남은 경우, 상위 조건, 반례 가능성을 별도 체크한다.

## `INSUFFICIENT_REVIEW_BASIS`

- Korean display name: 리뷰 근거 부족
- Definition: 정답·오답과 canonical 문항은 확인되지만 사용자 사고과정이나 피드백이 비어 있어 기제 태그를 확정하기 어려운 보류 태그.
- Positive criteria: unreviewed 상태이거나 self-review와 assistant feedback이 모두 없어 오답 메커니즘을 재구성할 수 없을 때 사용한다.
- Negative criteria: 리뷰 근거가 조금이라도 있어 낮은 확신의 기제 진단이 가능한 경우에는 해당 기제 태그와 low confidence를 사용한다.
- Neighboring tags: needs_review=true와 함께 사용하며, final_error_tags로 승격하지 않는 임시 품질 태그다.
- Representative review files: none in this corpus
- Suggested correction rule: canonical만으로 선택 이유를 추정하지 말고, 사용자 복기 또는 피드백 확보 후 다시 태깅한다.

## `RELATION_DIRECTION_REVERSAL`

- Korean display name: 관계 방향 전도
- Definition: A→B, 원인→결과, 주는 사람→받는 사람, 현재→목표, 입력→출력처럼 방향성이 명시된 관계를 반대로 잡은 오류.
- Positive criteria: 화살표, 비교 방향, 수식 대상, 교환·보상·통제의 방향이 실제 선지 판단에서 뒤집혔을 때 사용한다.
- Negative criteria: 명칭과 실제 속성을 혼동한 경우에는 TABLE_DIAGRAM_ENCODING_ERROR나 TEXTUAL_REDEFINITION_MISSED를 우선한다. 보완/대체 같은 방식어 오독은 TEXTUAL_REDEFINITION_MISSED를 우선한다.
- Neighboring tags: TABLE_DIAGRAM_ENCODING_ERROR는 표·기호·변수 입력 자체가 흔들릴 때, TEXTUAL_REDEFINITION_MISSED는 지문식 정의나 방식어를 다른 뜻으로 처리했을 때 우선한다.
- Representative review files: data/reviews/2019 언어이해 홀수형/q11.review.json, data/reviews/2021 추리논증 홀수형/q06.review.json, data/reviews/2021 추리논증 홀수형/q27.review.json, data/reviews/2023 언어이해 짝수형/q27.review.json
- Suggested correction rule: 방향어가 나오면 `A -> B` 형식으로 다시 쓰고, 선지가 같은 방향을 보존하는지 확인한다.

## `ROLE_ATTRIBUTION_ERROR`

- Korean display name: 역할·입장 귀속 오류
- Definition: 주장, 비판, 관점, 행위자, 통제 대상, 견해의 공통점 등을 잘못된 사람·집단·입장에 귀속한 오류.
- Positive criteria: A에게만 있는 술어를 B에도 붙이거나, 제3자에게 작용하는 규칙을 목표 대상에게 직접 작용한다고 본 경우 사용한다.
- Negative criteria: 같은 행위자의 조건 범위를 넓힌 경우에는 SCOPE_CONDITION_MISAPPLICATION을 우선한다.
- Neighboring tags: CONCEPT_LAYER_CONFUSION은 층위 자체가 바뀔 때, ROLE_ATTRIBUTION_ERROR는 귀속 대상이 바뀔 때 쓴다.
- Representative review files: data/reviews/2020 언어이해 홀수형/q20.review.json, data/reviews/2021 언어이해 홀수형/q28.review.json, data/reviews/2026 추리논증 홀수형/q01.review.json, data/reviews/2026 추리논증 홀수형/q08.review.json
- Suggested correction rule: 선지마다 `누가 / 무엇을 / 어떤 입장으로` 말하는지 세 칸으로 분리한다.

## `SCOPE_CONDITION_MISAPPLICATION`

- Korean display name: 범위·조건 오적용
- Definition: 조건, 예외, 한계, 상한·하한, 제도 영역, 단서, 적용 범위를 과확장·과축소하거나 누락한 오류.
- Positive criteria: 예외 생략, 일부 조건만으로 강한 결론 도출, 가능성을 보장으로 읽기, 이상/이하 경계값 누락에 사용한다.
- Negative criteria: 조건은 알았으나 여러 문항 전체에 끝까지 들고 가지 못한 경우에는 GLOBAL_CONSTRAINT_DROPPED를 우선한다.
- Neighboring tags: TEXTUAL_REDEFINITION_MISSED는 지문이 용어 자체를 새로 정의했을 때, FORMAL_CONDITION_ERROR는 형식 논리·대수 조건 조작이 핵심일 때 쓴다.
- Representative review files: data/reviews/2019 추리논증 홀수형/q13.review.json, data/reviews/2020 언어이해 홀수형/q16.review.json, data/reviews/2020 추리논증 홀수형/q02.review.json, data/reviews/2020 추리논증 홀수형/q06.review.json
- Suggested correction rule: 선지의 결론 앞에 필요한 조건을 모두 붙여 보고, 하나라도 빠지면 답 후보에서 제외한다.

## `TABLE_DIAGRAM_ENCODING_ERROR`

- Korean display name: 표·도식·변수 인코딩 오류
- Definition: 표, 도식, 그래프, 실험 설계, 변수 비교, 수치 임계값, 기호 라벨을 선지 판단 전에 올바른 문장·식·비교쌍으로 재부호화하지 못한 오류.
- Positive criteria: 현재/선호 열, ㉠·㉡ 라벨, 투과율/반사율, 점수/등수, 평균/분포, 실험 비교 변수, 임계값을 잘못 인코딩했을 때 사용한다.
- Negative criteria: 입력값은 맞게 읽었지만 전체 제약을 끝까지 유지하지 못했다면 GLOBAL_CONSTRAINT_DROPPED를 우선한다.
- Neighboring tags: RELATION_DIRECTION_REVERSAL은 인코딩된 값의 방향만 뒤집힌 경우 secondary로 자주 붙는다. FORMAL_CONDITION_ERROR는 식 조작 자체가 핵심일 때 우선한다.
- Representative review files: data/reviews/2019 추리논증 홀수형/q26.review.json, data/reviews/2019 추리논증 홀수형/q32.review.json, data/reviews/2020 추리논증 홀수형/q28.review.json, data/reviews/2020 추리논증 홀수형/q29.review.json
- Suggested correction rule: 표·그래프·실험 설계는 선지로 가기 전에 한 줄 식, 2x2 표, 또는 변수 비교쌍으로 다시 쓴다.

## `TEXTUAL_REDEFINITION_MISSED`

- Korean display name: 지문 정의 전환 누락
- Definition: 지문이 개념·용어·기준을 특수하게 정의했는데 일반적 의미나 이전 의미로 처리한 오류.
- Positive criteria: 인정, 복종, 대체, 제3자, 업무수탁자처럼 지문 안 정의가 선지 판단의 기준일 때 사용한다.
- Negative criteria: 용어 정의는 보존했지만 조건 일부를 놓친 경우에는 SCOPE_CONDITION_MISAPPLICATION을 우선한다.
- Neighboring tags: CONCEPT_LAYER_CONFUSION은 정의보다 층위 구분이 핵심일 때 쓴다.
- Representative review files: data/reviews/2022 언어이해 홀수형/q29.review.json, data/reviews/2022 추리논증 짝수형/q06.review.json, data/reviews/2026 언어이해 홀수형/q12.review.json
- Suggested correction rule: 핵심 용어 옆에 지문식 정의를 짧게 붙이고, 일상어 의미로 대체하지 않는다.

## `TIME_PRESSURE_OR_ATTENTION_LAPSE`

- Korean display name: 시간 압박·주의 저하
- Definition: 시간 압박, 피로, 후반부 집중력 저하, 소재 친숙성에 의한 경계심 저하가 1차 원인으로 확인되는 운영 오류.
- Positive criteria: 사용자 리뷰가 직접 시간·피로·대충 선택·글자 오독을 주요 원인으로 제시할 때 primary로 사용한다.
- Negative criteria: 운영 상태가 보조 설명일 뿐 명확한 기제 오류가 있으면 secondary로 둔다.
- Neighboring tags: CHOICE_VERIFICATION_FAILURE는 루틴 누락, TIME_PRESSURE_OR_ATTENTION_LAPSE는 그 루틴이 무너진 운영 원인이다.
- Representative review files: data/reviews/2023 언어이해 짝수형/q26.review.json, data/reviews/2026 언어이해 홀수형/q26.review.json
- Suggested correction rule: 후반부·시간 부족 문항은 선택 전 제한어와 비교어만이라도 별도로 표시한다.

## `UNWARRANTED_ASSUMPTION_ADDED`

- Korean display name: 무근거 가정 추가
- Definition: 지문이나 조건이 허용하지 않은 전제, 배경 설명, 경로, 사례, 일반론을 덧붙여 선지를 살린 오류.
- Positive criteria: 가능한 배경 설명을 직접 보충하거나, 불명확한 작용 경로를 임의로 제한했을 때 사용한다.
- Negative criteria: 명시 조건을 잘못 적용한 경우에는 SCOPE_CONDITION_MISAPPLICATION을 우선한다.
- Neighboring tags: CHOICE_VERIFICATION_FAILURE는 검산 누락, UNWARRANTED_ASSUMPTION_ADDED는 추가 전제가 판단을 움직였을 때 쓴다.
- Representative review files: data/reviews/2019 추리논증 홀수형/q08.review.json, data/reviews/2020 언어이해 홀수형/q03.review.json, data/reviews/2020 추리논증 홀수형/q31.review.json, data/reviews/2021 언어이해 홀수형/q10.review.json
- Suggested correction rule: 내가 덧붙인 문장이 지문에 있는지 표시하고, 없으면 선지 판단에서 제거한다.
