*** Settings ***
Library           Process
Library           VideoLibrary.py
Library           OperatingSystem
Library           Collections
Library           RequestsLibrary
Resource          keywords.robot
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

@{INPUT_VIDEOS_LIST}          tests/video.mp4
@{INPUT_IMAGES_LIST}          tests/image.png

*** Test Cases ***

Try To Test API With Wrong API Key
    [Documentation]    Try to upload a video with wrong an API key
    Run Keyword And Expect Error    *    Upload Media    ${INPUT_VIDEOS_LIST[${0}]}    ${API_URL}/upload     wrong_api_key

Upload, Process and Download Videos
    [Documentation]    Upload a video, process it, and download the result
    FOR    ${i}    IN RANGE    3
        ${s3_output_key}=    Upload Media    ${INPUT_VIDEOS_LIST[${0}]}    ${UPLOAD_ENDPOINT}&preset=11&crf=63
    END
    Wait Until All Workers Are Available    ${WORKER_STATUS_ENDPOINT}
    FOR    ${i}    IN RANGE    3
        Download Media    ${s3_output_key}    ${DOWNLOAD_ENDPOINT}    tests/video_encoded_${i}.mp4
        Remove File    tests/video_encoded_${i}.mp4
    END

Upload, Process and Download Images
    [Documentation]    Upload an image, process it, and download the result
#    ${LIST_LENGTH}=    Get Length    ${INPUT_IMAGES_LIST}
    FOR    ${i}    IN RANGE    15
        ${s3_output_key}=    Upload Media    ${INPUT_IMAGES_LIST[${0}]}    ${UPLOAD_ENDPOINT}&compression_level=2
    END
    Wait Until All Workers Are Available    ${WORKER_STATUS_ENDPOINT}

    FOR    ${i}    IN RANGE    15
        Download Media    ${s3_output_key}    ${DOWNLOAD_ENDPOINT}    tests/image_encoded_${i}.webp
    END

    ${expected_size_encoded}=    Get File Size    tests/image_encoded_0.webp
    FOR    ${i}    IN RANGE    15
        ${image_size_encoded}=    Get File Size    tests/image_encoded_${i}.webp
        Should Be Equal As Integers    ${expected_size_encoded}    ${image_size_encoded}    Image sizes do not match.
    END

    FOR    ${i}    IN RANGE    15
        Remove File    tests/image_encoded_${i}.webp
    END

Upload, Process and Download Images In Different Queue
    [Documentation]    Upload an image, process it, and download the result
    #FOR    ${index}    ${queue_name}    IN    ENUMERATE    @{QUEUE_NAMES}
    FOR    ${queue_name}    IN    @{QUEUE_NAMES}
        Log    Uploading image to queue ${queue_name}
        ${s3_output_key}=    Upload Media    ${INPUT_IMAGES_LIST[${0}]}    ${UPLOAD_ENDPOINT}&priority=5&compression_level=2&routing_key=${queue_name}
        Wait Until All Workers Are Available    ${WORKER_STATUS_ENDPOINT}
        Download Media    ${s3_output_key}    ${DOWNLOAD_ENDPOINT}    tests/image_encoded.webp
        Remove File    tests/image_encoded.webp
    END

*** Keywords ***
