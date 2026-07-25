from typing import IO


class UploadTooLarge(Exception):
    pass


class SizeLimitedFile:
    """Wraps an upload's file object so streaming to S3 aborts once max_bytes is exceeded."""

    def __init__(self, fileobj: IO[bytes], max_bytes: int):
        self._fileobj = fileobj
        self._max_bytes = max_bytes
        self._read_bytes = 0

    def read(self, size: int = -1) -> bytes:
        chunk: bytes = self._fileobj.read(size)
        self._read_bytes += len(chunk)
        if self._read_bytes > self._max_bytes:
            raise UploadTooLarge()
        return chunk
