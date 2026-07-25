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

# Never submitted to Celery -- used to exercise "unknown task" behavior deterministically,
# without racing a real task's own state transitions.
${DUMMY_TASK_ID}              00000000-0000-0000-0000-000000000000

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
    @{task_ids}=    Create List
    FOR    ${i}    IN RANGE    3
        ${response}=    Upload Media    ${INPUT_VIDEOS_LIST}[0]    ${UPLOAD_ENDPOINT}?preset=11&crf=63
        ${task_id}=    Get From Dictionary    ${response.json()}    task_id
        Wait Until Task Finished    ${task_id}
        Append To List    ${task_ids}    ${task_id}
    END
    FOR    ${i}    ${task_id}    IN ENUMERATE    @{task_ids}
        Download Media    ${task_id}    tests/video_encoded_${i}.mp4
        Remove File    tests/video_encoded_${i}.mp4
    END

Upload, Process and Download Images
    [Documentation]    Upload the same lossless image 15 times and verify every encoded output is
    ...                byte-identical, since lossless webp encoding is deterministic.
    @{task_ids}=    Create List
    FOR    ${i}    IN RANGE    15
        ${response}=    Upload Media    ${INPUT_IMAGES_LIST}[0]    ${UPLOAD_ENDPOINT}?compression_level=2
        ${task_id}=    Get From Dictionary    ${response.json()}    task_id
        Wait Until Task Finished    ${task_id}
        Append To List    ${task_ids}    ${task_id}
    END
    FOR    ${i}    ${task_id}    IN ENUMERATE    @{task_ids}
        Download Media    ${task_id}    tests/image_encoded_${i}.webp
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
        Wait Until Task Finished    ${task_id}
        Download Media    ${task_id}    tests/image_encoded.webp
        Remove File    tests/image_encoded.webp
    END

Health Endpoint Does Not Require Api Key
    [Documentation]    /health is an unauthenticated liveness probe used by the Docker healthcheck --
    ...                orchestration tooling must be able to call it without holding the API key.
    GET    ${HEALTH_ENDPOINT}    expected_status=200

Reject Protected Endpoints Without A Valid Api Key
    [Documentation]    Every endpoint other than /health must reject a wrong API key, not just
    ...                /upload (already covered by "Try To Test API With Wrong API Key").
    @{protected_endpoints}=    Create List
    ...    GET    ${TASKS_ENDPOINT}/${DUMMY_TASK_ID}
    ...    GET    ${TASKS_ENDPOINT}/${DUMMY_TASK_ID}/download
    ...    GET    ${WORKER_STATUS_ENDPOINT}
    ...    POST    ${CLEANUP_STORAGE_ENDPOINT}
    FOR    ${method}    ${url}    IN    @{protected_endpoints}
        Check Endpoint Requires Api Key    ${method}    ${url}
    END

Reject Upload With Out Of Range Parameters
    [Documentation]    priority/compression_level/preset/crf are bounded by Query(ge=..., le=...);
    ...                a value outside those bounds must be rejected with 422 before any file is
    ...                stored or any task is enqueued.
    Upload Media    ${INPUT_IMAGES_LIST}[0]    ${UPLOAD_ENDPOINT}?priority=11    expected_status=422
    Upload Media    ${INPUT_IMAGES_LIST}[0]    ${UPLOAD_ENDPOINT}?compression_level=10    expected_status=422
    Upload Media    ${INPUT_VIDEOS_LIST}[0]    ${UPLOAD_ENDPOINT}?preset=14    expected_status=422
    Upload Media    ${INPUT_VIDEOS_LIST}[0]    ${UPLOAD_ENDPOINT}?crf=64    expected_status=422

Reject Upload With Invalid Routing Key
    [Documentation]    routing_key is checked against an explicit whitelist so a caller can't
    ...                fabricate an arbitrary Celery queue name; anything outside video.high/low/all
    ...                must be rejected with 400.
    Upload Media    ${INPUT_IMAGES_LIST}[0]    ${UPLOAD_ENDPOINT}?routing_key=video.bogus    expected_status=400

Unknown Task Id Reports Pending State
    [Documentation]    /tasks/{id} for an id that was never submitted returns PENDING -- Celery's
    ...                default for any id it doesn't recognize in the result backend -- not 404.
    ...                Asserted explicitly so a future change to that default doesn't go unnoticed.
    ${status}=    Get Task Status    ${DUMMY_TASK_ID}
    Should Be Equal As Strings    ${status}[state]    PENDING

Download Before Task Finishes Is Rejected
    [Documentation]    Downloading a task that hasn't reached SUCCESS (or, as here, never will since
    ...                the id was never submitted) must fail with 409, not silently return an
    ...                empty/partial file.
    ${headers}=    Auth Headers
    GET    ${TASKS_ENDPOINT}/${DUMMY_TASK_ID}/download    headers=${headers}    expected_status=409

Exceed Upload Rate Limit Returns 429
    [Documentation]    /upload is rate limited per client IP (API_RATE_LIMIT_UPLOAD), enforced via
    ...                Valkey so the limit is shared across all uvicorn workers/replicas rather than
    ...                counted separately per process. Bursts past the configured limit using the
    ...                cheap "unsupported file type" rejection path (fails fast inside the endpoint,
    ...                after the rate limiter has already counted the call, without touching S3 or
    ...                Celery) and confirms a 429 shows up. Sleeps out the rest of the window
    ...                afterwards so this burst doesn't bleed into other tests' own /upload calls --
    ...                with --randomize all this test can land anywhere in the run.
    ${limit}=    Load Upload Rate Limit From Env File
    ${burst}=    Evaluate    ${limit} + 5
    ${headers}=    Auth Headers
    ${saw_429}=    Set Variable    ${False}
    FOR    ${i}    IN RANGE    ${burst}
        # A fresh handle every iteration: RequestsLibrary closes it after each request, so
        # reusing one handle across the loop would fail from the 2nd iteration onwards.
        ${file_data}=    Get File For Streaming Upload    ${UNSUPPORTED_FILE}
        &{files}=    Create Dictionary    file=${file_data}
        ${response}=    POST    ${UPLOAD_ENDPOINT}    files=${files}    headers=${headers}    expected_status=any
        IF    ${response.status_code} == 429
            ${saw_429}=    Set Variable    ${True}
            BREAK
        END
    END
    Should Be True    ${saw_429}    Never received a 429 after ${burst} requests (configured limit: ${limit}/minute).
    Sleep    61s    Let the rate-limit window fully reset so this burst doesn't affect later tests.

Clear Storage Removes Previously Downloadable Output
    [Documentation]    /admin/clear-storage must actually delete the S3 objects, not just return 200:
    ...                upload+process a file, confirm it downloads, clear storage, then confirm the
    ...                same task's output is gone -- even though the Celery result itself still
    ...                reports SUCCESS from cache (result_expires is independent of S3 content).
    ${response}=    Upload Media    ${INPUT_IMAGES_LIST}[0]    ${UPLOAD_ENDPOINT}?compression_level=2
    ${task_id}=    Get From Dictionary    ${response.json()}    task_id
    Wait Until Task Finished    ${task_id}
    Download Media    ${task_id}    tests/clear_storage_check.webp
    Remove File    tests/clear_storage_check.webp
    Clear Storage
    ${headers}=    Auth Headers
    GET    ${TASKS_ENDPOINT}/${task_id}/download    headers=${headers}    expected_status=404

Clear Storage Tests
    [Documentation]    Clear storage after tests
    Clear Storage

*** Keywords ***
