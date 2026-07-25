*** Settings ***
Library           Process
Library           OperatingSystem
Library           Collections
Library           String
Library           RequestsLibrary

*** Variables ***
${API_URL}                     http://localhost:5500
${RABBITMQ_URL}                http://localhost:15672
${FLOWER_URL}                  http://localhost:5555

${API_ENV_FILE}                 parallel/services/api/env/variables.api.env
${API_KEY}                      ${EMPTY}

${UPLOAD_ENDPOINT}             ${API_URL}/v1/upload
${HEALTH_ENDPOINT}              ${API_URL}/health
${WORKER_STATUS_ENDPOINT}      ${API_URL}/health/workers
${TASKS_ENDPOINT}                ${API_URL}/v1/tasks
${CLEANUP_STORAGE_ENDPOINT}    ${API_URL}/v1/admin/clear-storage

*** Keywords ***

Load Api Key From Env File
    [Documentation]    The API key is generated locally by scripts/init_env.py (see
    ...                Makefile's env-init target) rather than hardcoded, so tests read
    ...                it back from the generated env file instead of assuming a fixed
    ...                value.
    ${content}=    Get File    ${API_ENV_FILE}
    @{matches}=    Get Regexp Matches    ${content}    API_KEY=(.+)    1
    RETURN    ${matches}[0]

Auth Headers
    [Documentation]    Single source of truth for the X-API-Key header, so tests never hardcode it.
    [Arguments]    ${api_key}=${API_KEY}
    ${headers}=    Create Dictionary    X-API-Key=${api_key}
    RETURN    ${headers}

Check Endpoint Requires Api Key
    [Documentation]    Every protected endpoint must reject a missing/wrong key with 403 on its own,
    ...                not just /upload -- called once per endpoint so a Depends(require_api_key)
    ...                accidentally dropped from any single one of them fails this test instead of
    ...                going unnoticed. ${method} must be a RequestsLibrary keyword name (GET/POST/...).
    [Arguments]    ${method}    ${url}
    ${headers}=    Auth Headers    api_key=wrong_api_key
    Run Keyword    ${method}    ${url}    headers=${headers}    expected_status=403

Load Upload Rate Limit From Env File
    [Documentation]    Reads API_RATE_LIMIT_UPLOAD (e.g. "20/minute") so the rate-limit test bursts
    ...                enough requests to exceed whatever is actually configured, instead of
    ...                hardcoding an assumed limit that could silently drift from the env template.
    ${content}=    Get File    ${API_ENV_FILE}
    @{matches}=    Get Regexp Matches    ${content}    API_RATE_LIMIT_UPLOAD=(\\d+)    1
    RETURN    ${matches}[0]

Clear Storage
    [Arguments]    ${api_url}=${CLEANUP_STORAGE_ENDPOINT}
    ${headers}=    Auth Headers
    POST    ${api_url}    headers=${headers}    expected_status=200
    Log    Storage cleared successfully.

Check One Worker Is Connected
    [Arguments]    ${api_url}=${WORKER_STATUS_ENDPOINT}
    ${headers}=    Auth Headers
    ${response}=    GET    ${api_url}    headers=${headers}    expected_status=200
    ${worker_count}=    Get From Dictionary    ${response.json()}    worker_count    0
    Should Be True    ${worker_count} > 0    All workers are not connected.

Wait Until One Worker Is Connected
    [Arguments]    ${api_url}=${WORKER_STATUS_ENDPOINT}    ${timeout}=120 sec    ${interval}=1 sec
    Log    Waiting for workers to be connected...
    Wait Until Keyword Succeeds    ${timeout}    ${interval}    Check One Worker Is Connected    ${api_url}

Check Can Ping Url
    [Arguments]    ${url}    ${api_key}=${API_KEY}
    ${headers}=    Auth Headers    ${api_key}
    GET    ${url}    headers=${headers}    expected_status=200

Wait Can Ping Url
    [Arguments]    ${url}    ${timeout}=120 sec    ${interval}=1 sec    ${api_key}=${API_KEY}
    Log    Waiting for ${url} to be reachable...
    Wait Until Keyword Succeeds    ${timeout}    ${interval}    Check Can Ping Url    ${url}    ${api_key}

Start Docker Compose Environment
    [Documentation]    Build and start the full stack, then wait until it can actually accept work.
    ${result}=    Run Process    make    start
    Should Be Equal As Integers    ${result.rc}    0    Docker compose start failed: ${result.stderr}
    ${api_key}=    Load Api Key From Env File
    Set Suite Variable    ${API_KEY}    ${api_key}
    Wait Can Ping Url    ${HEALTH_ENDPOINT}
    Wait Can Ping Url    ${RABBITMQ_URL}
    Wait Until One Worker Is Connected

Stop Docker Compose Environment
    [Documentation]    Clear test data and stop the stack.
    Clear Storage
    ${result}=    Run Process    make    stop
    Should Be Equal As Integers    ${result.rc}    0    Docker compose stop failed: ${result.stderr}
    Run Keyword And Expect Error    *    Check Can Ping Url    ${HEALTH_ENDPOINT}
    Run Keyword And Expect Error    *    Check Can Ping Url    ${RABBITMQ_URL}
    Run Keyword And Expect Error    *    Check One Worker Is Connected

Upload Media
    [Documentation]    Upload a file and return the raw response, so callers can inspect status,
    ...                task_id or s3 keys as needed. Pass expected_status to assert error responses
    ...                (e.g. 400/403/413) without wrapping the call in Run Keyword And Expect Error.
    [Arguments]    ${file_path}    ${upload_endpoint}=${UPLOAD_ENDPOINT}    ${api_key}=${API_KEY}    ${expected_status}=200
    ${headers}=    Auth Headers    ${api_key}
    ${file_data}=    Get File For Streaming Upload    ${file_path}
    &{files}=    Create Dictionary    file=${file_data}
    ${response}=    POST    ${upload_endpoint}    files=${files}    headers=${headers}    expected_status=${expected_status}
    RETURN    ${response}

Get Task Status
    [Arguments]    ${task_id}    ${api_key}=${API_KEY}
    ${headers}=    Auth Headers    ${api_key}
    ${response}=    GET    ${TASKS_ENDPOINT}/${task_id}    headers=${headers}    expected_status=200
    RETURN    ${response.json()}

Wait Until Task Reaches State
    [Documentation]    Poll /tasks/{id} until it reaches ${expected_state}. Fails immediately if it
    ...                reaches the other terminal state instead of retrying until the timeout, so a
    ...                test reports a wrong outcome fast rather than just timing out.
    [Arguments]    ${task_id}    ${expected_state}    ${timeout: int}=120    ${interval: int}=2
    ${other_state}=    Set Variable If    "${expected_state}" == "SUCCESS"    FAILURE    SUCCESS
    FOR    ${i}    IN RANGE    ${{$timeout // $interval}}
        ${status}=    Get Task Status    ${task_id}
        ${state}=    Get From Dictionary    ${status}    state
        Return From Keyword If    "${state}" == "${expected_state}"    ${status}
        Run Keyword If    "${state}" == "${other_state}"
        ...    Fail    Task ${task_id} reached ${state} instead of the expected ${expected_state}: ${status}
        Sleep    ${interval}s
    END
    Fail    Task ${task_id} did not reach ${expected_state} within ${timeout}s (last state: ${state})

Wait Until Task Finished
    [Documentation]    Poll /tasks/{id} until it reaches SUCCESS. Fails fast on FAILURE instead of
    ...                retrying until the timeout, so a broken encode is reported quickly.
    [Arguments]    ${task_id}    ${timeout: int}=120    ${interval: int}=2
    ${status}=    Wait Until Task Reaches State    ${task_id}    SUCCESS    ${timeout}    ${interval}
    RETURN    ${status}

Wait Until Task Fails
    [Documentation]    Poll /tasks/{id} until it reaches FAILURE. Fails the test if it succeeds
    ...                instead, since that would mean the negative test case stopped reproducing.
    [Arguments]    ${task_id}    ${timeout: int}=120    ${interval: int}=2
    ${status}=    Wait Until Task Reaches State    ${task_id}    FAILURE    ${timeout}    ${interval}
    RETURN    ${status}

Download Media
    [Documentation]    Download a finished task's output. The API resolves the S3 key itself from
    ...                the task's own result, so this only ever needs the task_id -- callers cannot
    ...                (and don't need to) pass an arbitrary S3 key.
    [Arguments]    ${task_id}    ${output_path}    ${api_key}=${API_KEY}
    ${headers}=    Auth Headers    ${api_key}
    ${response}=    Wait Until Keyword Succeeds    2 min    2 sec
    ...    GET    ${TASKS_ENDPOINT}/${task_id}/download    headers=${headers}    expected_status=200
    Create Binary File    ${output_path}    ${response.content}
    File Should Exist    ${output_path}    Output file does not exist.
