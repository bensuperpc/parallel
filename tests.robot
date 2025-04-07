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
@{QUEUE_NAMES}    video.all    video.low    video.high

${UPLOAD_ENDPOINT}             ${API_URL}/upload?apikey=${API_KEY}
${DOWNLOAD_ENDPOINT}           ${API_URL}/download?apikey=${API_KEY}
${API_STATUS_ENDPOINT}         ${API_URL}/status/api?apikey=${API_KEY}
${WORKER_STATUS_ENDPOINT}      ${API_URL}/status/worker?apikey=${API_KEY}
${CLEANUP_STORAGE_ENDPOINT}    ${API_URL}/clear_storage?apikey=${API_KEY}

${INPUT_VIDEO_FILE}          tests/video.mp4
${INPUT_IMAGE_FILE}          tests/image.png

*** Test Cases ***

Try To Test API Without API Key
    [Documentation]    Try to upload a video without an API key
    Run Keyword And Expect Error    *    Upload Media    ${INPUT_VIDEO_FILE}    ${API_URL}/upload

Upload, Process and Download Videos
    [Documentation]    Upload a video, process it, and download the result
    FOR    ${i}    IN RANGE    2
        ${s3_output_key}=    Upload Media    ${INPUT_VIDEO_FILE}    ${UPLOAD_ENDPOINT}&preset=11&crf=63
    END
    Wait Until All Workers Are Available    ${WORKER_STATUS_ENDPOINT}
    FOR    ${i}    IN RANGE    2
        Download Media    ${s3_output_key}    ${DOWNLOAD_ENDPOINT}    tests/video_encoded_${i}.mp4
        Remove File    tests/video_encoded_${i}.mp4
    END

Upload, Process and Download Images
    [Documentation]    Upload an image, process it, and download the result
    FOR    ${i}    IN RANGE    10
        ${s3_output_key}=    Upload Media    ${INPUT_IMAGE_FILE}    ${UPLOAD_ENDPOINT}&compression_level=2
    END
    Wait Until All Workers Are Available    ${WORKER_STATUS_ENDPOINT}

    FOR    ${i}    IN RANGE    10
        Download Media    ${s3_output_key}    ${DOWNLOAD_ENDPOINT}    tests/image_encoded_${i}.webp
    END

    ${expected_size_encoded}=    Get File Size    tests/image_encoded_0.webp
    FOR    ${i}    IN RANGE    10
        ${image_size_encoded}=    Get File Size    tests/image_encoded_${i}.webp
        Should Be Equal As Integers    ${expected_size_encoded}    ${image_size_encoded}    Image sizes do not match.
    END
    
    FOR    ${i}    IN RANGE    10
        Remove File    tests/image_encoded_${i}.webp
    END

Upload, Process and Download Images In Different Queue
    [Documentation]    Upload an image, process it, and download the result
    #FOR    ${index}    ${queue_name}    IN    ENUMERATE    @{QUEUE_NAMES}
    FOR    ${queue_name}    IN    @{QUEUE_NAMES}
        Log    Uploading image to queue ${queue_name}
        ${s3_output_key}=    Upload Media    ${INPUT_IMAGE_FILE}    ${UPLOAD_ENDPOINT}&priority=5&compression_level=2&routing_key=${queue_name}
        Wait Until All Workers Are Available    ${WORKER_STATUS_ENDPOINT}
        Download Media    ${s3_output_key}    ${DOWNLOAD_ENDPOINT}    tests/image_encoded.webp
        Remove File    tests/image_encoded.webp
    END

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
    [Arguments]    ${url}
    ${response}    GET    ${url}
    Run Keyword If    ${response.status_code} != 200    Fail    Request failed with code ${response.status_code}

Wait Can Ping Url
    [Arguments]    ${url}    ${timeout}=120 sec    ${interval}=1 sec
    Log    Waiting for ${url} to be reachable...
    Wait Until Keyword Succeeds    ${timeout}    ${interval}    Check Can Ping Url    ${url}

Start Docker Compose Environment
    [Documentation]    Wait for the Docker containers to be up and running.
    Makefile Command    start
    Wait Can Ping Url    ${API_STATUS_ENDPOINT}
    Wait Can Ping Url    ${RABBITMQ_URL}
    #Wait Can Ping Url    ${FLOWER_URL}
    Wait Until One Worker Is Connected    ${WORKER_STATUS_ENDPOINT}

Stop Docker Compose Environment
    [Documentation]   Stop docker containers
    Clear Storage     api_url=${CLEANUP_STORAGE_ENDPOINT}
    Makefile Command    stop
    Run Keyword And Expect Error    *    Check Can Ping Url    ${API_STATUS_ENDPOINT}
    Run Keyword And Expect Error    *    Check Can Ping Url    ${RABBITMQ_URL}
    Run Keyword And Expect Error    *    Check Can Ping Url    ${FLOWER_URL}
    Run Keyword And Expect Error    *    Check One Worker Is Connected    ${WORKER_STATUS_ENDPOINT}

Upload Media
    [Arguments]    ${video_file}    ${upload_endpoint}
    Log    Uploading video file: ${video_file} to ${upload_endpoint}
    ${result}=    Upload Video    ${video_file}    ${upload_endpoint}
    Log    API response: ${result}
    ${s3_output_key}=    Get From Dictionary    ${result}    s3_output_key
    Should Not Be Empty    ${s3_output_key}    s3_output_key is empty.
    ${s3_input_key}=    Get From Dictionary    ${result}    s3_input_key
    Should Not Be Empty    ${s3_input_key}    s3_input_key is empty.
    ${task_id}=    Get From Dictionary    ${result}    task_id
    Should Not Be Empty    ${task_id}    task_id is empty.
    RETURN    ${s3_output_key}

Download Media
    [Arguments]    ${s3_output_key}    ${download_endpoint}    ${output_filename}
    Download Video    ${s3_output_key}    ${download_endpoint}    ${output_filename}
    File Should Exist    ${output_filename}    Output file does not exist.
