*** Settings ***
Library           Process
Library           VideoLibrary.py
Library           OperatingSystem
Library           Collections
Library           RequestsLibrary

*** Variables ***
${API_URL}             http://localhost:5500
${RABBITMQ_URL}        http://localhost:15672
${FLOWER_URL}          http://localhost:5555

${API_KEY}             secret123

${UPLOAD_ENDPOINT}             ${API_URL}/upload?apikey=${API_KEY}
${DOWNLOAD_ENDPOINT}           ${API_URL}/download?apikey=${API_KEY}
${API_STATUS_ENDPOINT}         ${API_URL}/status/api?apikey=${API_KEY}
${WORKER_STATUS_ENDPOINT}      ${API_URL}/status/worker?apikey=${API_KEY}
${CLEANUP_STORAGE_ENDPOINT}    ${API_URL}/clear_storage?apikey=${API_KEY}

*** Keywords ***

Clear Storage
    [Arguments]    ${api_url}
    ${headers}=    Create Dictionary    X-API-Key=secret123
    ${response}    GET    ${api_url}    headers=${headers}
    Log    Storage cleared successfully.

Check One Worker Is Connected
    [Arguments]    ${api_url}
    ${headers}=    Create Dictionary    X-API-Key=secret123
    ${response}=    GET    ${api_url}    headers=${headers}
    Run Keyword If    ${response.status_code} != 200    Fail    Request failed with code ${response.status_code}
    ${worker_status}=    Set Variable    ${response.json()}
    ${worker_count}=    Get From Dictionary    ${worker_status}    worker_count    0
    Should Be True    ${worker_count} > 0    All workers are not connected.

Wait Until One Worker Is Connected
    [Arguments]    ${api_url}    ${timeout}=120 sec    ${interval}=1 sec
    Log    Waiting for workers to be connected...
    Wait Until Keyword Succeeds    ${timeout}    ${interval}    Check One Worker Is Connected    ${api_url}

Check All Workers Are Available
    [Arguments]    ${api_url}
    ${response}    GET    ${api_url}
    Run Keyword If    ${response.status_code} != 200    Fail    Request failed with code ${response.status_code}
    ${worker_status}    Set Variable    ${response.json()}
    Log    Worker status: ${worker_status}
    ${all_available}    Get From Dictionary    ${worker_status}    all_workers_available    False
    Should Be True    ${all_available}    All workers are not available.

Wait Until All Workers Are Available
    [Arguments]    ${api_url}    ${timeout}=120 sec    ${interval}=1 sec
    Log    Waiting for all workers to be available...
    Wait Until Keyword Succeeds    ${timeout}    ${interval}    Check All Workers Are Available    ${api_url}

Check Can Ping Url
    [Arguments]    ${url}    ${api_key}=secret123
    ${headers}=    Create Dictionary    X-API-Key=${api_key}
    ${response}    GET    ${url}    headers=${headers}
    Run Keyword If    ${response.status_code} != 200    Fail    Request failed with code ${response.status_code}

Wait Can Ping Url
    [Arguments]    ${url}    ${timeout}=120 sec    ${interval}=1 sec    ${api_key}=secret123
    Log    Waiting for ${url} to be reachable...
    Wait Until Keyword Succeeds    ${timeout}    ${interval}    Check Can Ping Url    ${url}    ${api_key}

Start Docker Compose Environment
    [Documentation]    Wait for the Docker containers to be up and running.
    ${result}=     Run Process    make    start
    Should Be Equal As Integers    ${result.rc}    0    Docker compose start failed.
    Wait Can Ping Url    ${API_STATUS_ENDPOINT}
    Wait Can Ping Url    ${RABBITMQ_URL}
    #Wait Can Ping Url    ${FLOWER_URL}
    Wait Until One Worker Is Connected    ${WORKER_STATUS_ENDPOINT}

Stop Docker Compose Environment
    [Documentation]   Stop docker containers
    Clear Storage     api_url=${CLEANUP_STORAGE_ENDPOINT}
    ${result} =     Run Process    make    stop
    Should Be Equal As Integers    ${result.rc}    0    Docker compose stop failed.
    Run Keyword And Expect Error    *    Check Can Ping Url    ${API_STATUS_ENDPOINT}
    Run Keyword And Expect Error    *    Check Can Ping Url    ${RABBITMQ_URL}
    Run Keyword And Expect Error    *    Check Can Ping Url    ${FLOWER_URL}
    Run Keyword And Expect Error    *    Check One Worker Is Connected    ${WORKER_STATUS_ENDPOINT}

Upload Media
    [Arguments]    ${video_file}    ${upload_endpoint}    ${api_key}=secret123
    Log    Uploading video file: ${video_file} to ${upload_endpoint}
    ${result}=    Upload Video    ${video_file}    ${upload_endpoint}    ${api_key}
    Log    API response: ${result}
    ${s3_output_key}=    Get From Dictionary    ${result}    s3_output_key
    Should Not Be Empty    ${s3_output_key}    s3_output_key is empty.
    ${s3_input_key}=    Get From Dictionary    ${result}    s3_input_key
    Should Not Be Empty    ${s3_input_key}    s3_input_key is empty.
    ${task_id}=    Get From Dictionary    ${result}    task_id
    Should Not Be Empty    ${task_id}    task_id is empty.
    RETURN    ${s3_output_key}

Download Media
    [Arguments]    ${s3_output_key}    ${download_endpoint}    ${output_filename}    ${api_key}=secret123
    Download Video    ${s3_output_key}    ${download_endpoint}    ${output_filename}   ${api_key}
    File Should Exist    ${output_filename}    Output file does not exist.
