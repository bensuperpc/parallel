*** Settings ***
Library           Process
Library           OperatingSystem
Library           Collections
Library           RequestsLibrary

*** Variables ***
${API_URL}                     http://localhost:5500
${RABBITMQ_URL}                http://localhost:15672
${FLOWER_URL}                  http://localhost:5555

${API_KEY}                     secret123

${UPLOAD_ENDPOINT}             ${API_URL}/upload
${DOWNLOAD_ENDPOINT}           ${API_URL}/download
${API_STATUS_ENDPOINT}         ${API_URL}/status/api
${WORKER_STATUS_ENDPOINT}      ${API_URL}/status/worker
${TASK_STATUS_ENDPOINT}        ${API_URL}/status/task
${CLEANUP_STORAGE_ENDPOINT}    ${API_URL}/clear_storage

*** Keywords ***

Auth Headers
    [Documentation]    Single source of truth for the X-API-Key header, so tests never hardcode it.
    [Arguments]    ${api_key}=${API_KEY}
    ${headers}=    Create Dictionary    X-API-Key=${api_key}
    RETURN    ${headers}

Clear Storage
    [Arguments]    ${api_url}=${CLEANUP_STORAGE_ENDPOINT}
    ${headers}=    Auth Headers
    GET    ${api_url}    headers=${headers}    expected_status=200
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
    Wait Can Ping Url    ${API_STATUS_ENDPOINT}
    Wait Can Ping Url    ${RABBITMQ_URL}
    Wait Until One Worker Is Connected

Stop Docker Compose Environment
    [Documentation]    Clear test data and stop the stack.
    Clear Storage
    ${result}=    Run Process    make    stop
    Should Be Equal As Integers    ${result.rc}    0    Docker compose stop failed: ${result.stderr}
    Run Keyword And Expect Error    *    Check Can Ping Url    ${API_STATUS_ENDPOINT}
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
    ${response}=    GET    ${TASK_STATUS_ENDPOINT}/${task_id}    headers=${headers}    expected_status=200
    RETURN    ${response.json()}

Wait Until Task Finished
    [Documentation]    Poll /status/task/{id} until it reaches SUCCESS. Fails immediately on FAILURE
    ...                instead of retrying until the timeout, so a broken encode is reported fast.
    [Arguments]    ${task_id}    ${timeout: int}=120    ${interval: int}=2
    FOR    ${i}    IN RANGE    ${{$timeout // $interval}}
        ${status}=    Get Task Status    ${task_id}
        ${state}=    Get From Dictionary    ${status}    state
        Return From Keyword If    "${state}" == "SUCCESS"    ${status}
        Run Keyword If    "${state}" == "FAILURE"    Fail    Task ${task_id} failed: ${status}
        Sleep    ${interval}s
    END
    Fail    Task ${task_id} did not finish within ${timeout}s (last state: ${state})

Wait Until Task Fails
    [Documentation]    Poll /status/task/{id} until it reaches FAILURE. Fails the test if it succeeds
    ...                instead, since that would mean the negative test case stopped reproducing.
    [Arguments]    ${task_id}    ${timeout: int}=120    ${interval: int}=2
    FOR    ${i}    IN RANGE    ${{$timeout // $interval}}
        ${status}=    Get Task Status    ${task_id}
        ${state}=    Get From Dictionary    ${status}    state
        Return From Keyword If    "${state}" == "FAILURE"    ${status}
        Run Keyword If    "${state}" == "SUCCESS"    Fail    Task ${task_id} was expected to fail but succeeded: ${status}
        Sleep    ${interval}s
    END
    Fail    Task ${task_id} did not reach a final state within ${timeout}s (last state: ${state})

Download Media
    [Arguments]    ${s3_output_key}    ${output_path}    ${download_endpoint}=${DOWNLOAD_ENDPOINT}    ${api_key}=${API_KEY}
    ${headers}=    Auth Headers    ${api_key}
    &{params}=    Create Dictionary    s3_output_key=${s3_output_key}
    ${response}=    Wait Until Keyword Succeeds    2 min    2 sec
    ...    GET    ${download_endpoint}    headers=${headers}    params=${params}    expected_status=200
    Create Binary File    ${output_path}    ${response.content}
    File Should Exist    ${output_path}    Output file does not exist.
