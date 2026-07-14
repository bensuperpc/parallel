*** Settings ***
Library           OperatingSystem
Library           Collections
Library           RequestsLibrary
Resource          keywords.robot
Suite Setup       Start Docker Compose Environment
Suite Teardown    Stop Docker Compose Environment

*** Variables ***
@{QUEUE_NAMES}                video.all    video.low    video.high

@{INPUT_VIDEOS_LIST}          tests/video.mp4
@{INPUT_IMAGES_LIST}          tests/image.png
${INVALID_VIDEO}              tests/invalid.mp4
${UNSUPPORTED_FILE}           tests/unsupported.txt

*** Test Cases ***

Try To Test API With Wrong API Key
    [Documentation]    Uploading with an invalid API key must be rejected with 403.
    Upload Media    ${INPUT_VIDEOS_LIST}[0]    api_key=wrong_api_key    expected_status=403

Reject Upload With Unsupported File Type
    [Documentation]    A file extension the API doesn't handle must be rejected with 400, and must
    ...                not reach the queue.
    Upload Media    ${UNSUPPORTED_FILE}    expected_status=400

Upload Invalid Video Reports Task Failure
    [Documentation]    A file that passes the extension check but that ffmpeg can't decode must
    ...                surface as a FAILURE via the task status endpoint instead of disappearing
    ...                silently (the failure mode the API had before task tracking existed).
    ${response}=    Upload Media    ${INVALID_VIDEO}
    ${task_id}=    Get From Dictionary    ${response.json()}    task_id
    Wait Until Task Fails    ${task_id}    timeout=90

Upload, Process and Download Videos
    [Documentation]    Upload the same video 3 times back to back and verify each job individually
    ...                reaches SUCCESS and its own output can be downloaded, rather than assuming
    ...                the whole system is done once the queue looks empty.
    @{output_keys}=    Create List
    FOR    ${i}    IN RANGE    3
        ${response}=    Upload Media    ${INPUT_VIDEOS_LIST}[0]    ${UPLOAD_ENDPOINT}?preset=11&crf=63
        ${task_id}=    Get From Dictionary    ${response.json()}    task_id
        ${s3_output_key}=    Get From Dictionary    ${response.json()}    s3_output_key
        Wait Until Task Finished    ${task_id}
        Append To List    ${output_keys}    ${s3_output_key}
    END
    FOR    ${i}    ${s3_output_key}    IN ENUMERATE    @{output_keys}
        Download Media    ${s3_output_key}    tests/video_encoded_${i}.mp4
        Remove File    tests/video_encoded_${i}.mp4
    END

Upload, Process and Download Images
    [Documentation]    Upload the same lossless image 15 times and verify every encoded output is
    ...                byte-identical, since lossless webp encoding is deterministic.
    @{output_keys}=    Create List
    FOR    ${i}    IN RANGE    15
        ${response}=    Upload Media    ${INPUT_IMAGES_LIST}[0]    ${UPLOAD_ENDPOINT}?compression_level=2
        ${task_id}=    Get From Dictionary    ${response.json()}    task_id
        ${s3_output_key}=    Get From Dictionary    ${response.json()}    s3_output_key
        Wait Until Task Finished    ${task_id}
        Append To List    ${output_keys}    ${s3_output_key}
    END
    FOR    ${i}    ${s3_output_key}    IN ENUMERATE    @{output_keys}
        Download Media    ${s3_output_key}    tests/image_encoded_${i}.webp
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
    [Documentation]    Route the same job to each priority queue in turn and confirm it still
    ...                completes and is downloadable.
    FOR    ${queue_name}    IN    @{QUEUE_NAMES}
        Log    Uploading image to queue ${queue_name}
        ${response}=    Upload Media    ${INPUT_IMAGES_LIST}[0]    ${UPLOAD_ENDPOINT}?priority=5&compression_level=2&routing_key=${queue_name}
        ${task_id}=    Get From Dictionary    ${response.json()}    task_id
        ${s3_output_key}=    Get From Dictionary    ${response.json()}    s3_output_key
        Wait Until Task Finished    ${task_id}
        Download Media    ${s3_output_key}    tests/image_encoded.webp
        Remove File    tests/image_encoded.webp
    END

Clear Storage Tests
    [Documentation]    Clear storage after tests
    Clear Storage

*** Keywords ***
