*** Settings ***
Library           Process
Library           VideoLibrary.py
Library           OperatingSystem
Library           Collections
Library           RequestsLibrary
Suite Setup       Start Docker Compose Environment
Suite Teardown    Stop Docker Compose Environment

*** Variables ***
${API_URL}             http://localhost:5500
${RABBITMQ_URL}        http://localhost:15672
${FLOWER_URL}          http://localhost:5555

${API_KEY}             secret123
${UPLOAD_ENDPOINT}     ${API_URL}/upload?apikey=${API_KEY}
${DOWNLOAD_ENDPOINT}   ${API_URL}/download?apikey=${API_KEY}
${API_STATUS_ENDPOINT}     ${API_URL}/status/api?apikey=${API_KEY}
${WORKER_STATUS_ENDPOINT}  ${API_URL}/status/worker?apikey=${API_KEY}
${CLEANUP_STORAGE_ENDPOINT}  ${API_URL}/clear_storage?apikey=${API_KEY}

${VIDEO_FILE}          video.mp4
${OUTPUT_FILENAME}     video_encoded.mp4


*** Test Cases ***
Upload, Process and Download Video
    [Documentation]    Upload a video, process it, and download the result.
    ${s3_output_key}=    Upload And Validate Video    ${VIDEO_FILE}    ${UPLOAD_ENDPOINT}
    Wait All Workers Available    45s
    Download And Validate Video    ${s3_output_key}    ${DOWNLOAD_ENDPOINT}    ${OUTPUT_FILENAME}

*** Keywords ***

Clear Storage
    [Arguments]    ${api_url}
    ${response}    GET    ${api_url}
    Log    Storage cleared successfully.

Check One Worker Is Connected
    [Arguments]    ${api_url}
    ${response}    GET    ${api_url}
    Run Keyword If    ${response.status_code} != 200    Fail    Request failed with code ${response.status_code}
    ${worker_status}    Set Variable    ${response.json()}
    ${worker_count}    Get From Dictionary    ${worker_status}    worker_count    0
    Should Be True    ${worker_count} > 0    All workers are not connected.

Wait Until One Worker Is Connected
    [Arguments]    ${api_url}    ${timeout}=90s    ${interval}=2s
    Log    Waiting for workers to be connected...
    Wait Until Keyword Succeeds    ${timeout}    ${interval}    Check One Worker Is Connected    ${api_url}

Check All Workers Are Free
    [Arguments]    ${api_url}
    ${response}    GET    ${api_url}
    Run Keyword If    ${response.status_code} != 200    Fail    Request failed with code ${response.status_code}
    ${worker_status}    Set Variable    ${response.json()}
    Log    Worker status: ${worker_status}
    ${all_available}    Get From Dictionary    ${worker_status}    all_workers_available    False
    Should Be True    ${all_available}    All workers are not available.

Wait Until All Workers Are Free
    [Arguments]    ${api_url}    ${timeout}=90s    ${interval}=2s
    Log    Waiting for all workers to be available...
    Wait Until Keyword Succeeds    ${timeout}    ${interval}    Check All Workers Are Free    ${api_url}

Check Can Ping Url
    [Arguments]    ${url}
    ${response}    GET    ${url}

Wait Can Ping Url
    [Arguments]    ${url}    ${timeout}=90s    ${interval}=2s
    Log    Waiting for ${url} to be reachable...
    Wait Until Keyword Succeeds    ${timeout}    ${interval}    Check Can Ping Url    ${url}

Start Docker Compose Environment
    [Documentation]    Wait for the Docker containers to be up and running.
    Start Docker Compose
    Wait Can Ping Url    ${API_STATUS_ENDPOINT}
    Wait Can Ping Url    ${RABBITMQ_URL}
    #Wait Can Ping Url    ${FLOWER_URL}
    Wait Until One Worker Is Connected    ${WORKER_STATUS_ENDPOINT}

Stop Docker Compose Environment
    [Documentation]   Stop docker containers
    Clear Storage     api_url=${CLEANUP_STORAGE_ENDPOINT}
    Stop Docker Compose
    Run Keyword And Expect Error    *    Check Can Ping Url    ${API_STATUS_ENDPOINT}
    Run Keyword And Expect Error    *    Check Can Ping Url    ${RABBITMQ_URL}
    Run Keyword And Expect Error    *    Check Can Ping Url    ${FLOWER_URL}
    Run Keyword And Expect Error    *    Check One Worker Is Connected    ${WORKER_STATUS_ENDPOINT}

Upload And Validate Video
    [Arguments]    ${video_file}    ${upload_endpoint}
    ${result}=    Upload Video    ${video_file}    ${upload_endpoint}
    Log    API response: ${result}
    ${s3_output_key}=    Get From Dictionary    ${result}    s3_output_key
    Should Not Be Empty    ${s3_output_key}    s3_output_key is empty.
    ${task_id}=    Get From Dictionary    ${result}    task_id
    Should Not Be Empty    ${task_id}    task_id is empty.
    RETURN    ${s3_output_key}

Wait All Workers Available
    [Arguments]    ${timeout}=45s
    Log    Attente de ${timeout} pour que l'encodage soit terminé...
    Wait Until All Workers Are Free    ${WORKER_STATUS_ENDPOINT}

Download And Validate Video
    [Arguments]    ${s3_output_key}    ${download_endpoint}    ${output_filename}
    Download Video    ${s3_output_key}    ${download_endpoint}    ${output_filename}
    File Should Exist    ${output_filename}    Fichier de sortie non trouvé.
    Remove File    ${OUTPUT_FILENAME}
