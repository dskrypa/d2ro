"""
Construct adapters / sub-constructs for save files.

:author: Doug Skrypa
"""

import logging
from io import BytesIO

from construct import Subconstruct, ValidationError, Int32ul

log = logging.getLogger(__name__)
__all__ = ['Checksum']


class Checksum(Subconstruct):  # noqa
    # Copied from nier_replicant; may not be needed here, most likely different if it has one
    def __init__(self, seek: int, read: int):
        super().__init__(Int32ul)
        self._seek = seek  # Number of bytes to seek backwards from the position of the checksum struct
        self._read = read  # Number of bytes from the backwards seek position to read / include in the sum

    def _get_checksum(self, stream: BytesIO):
        pos = stream.tell()
        stream.seek(pos - self._seek)
        checksum = sum(stream.read(self._read))
        stream.seek(pos)
        return checksum

    def _parse(self, stream, context, path):
        checksum = self._get_checksum(stream)
        parsed = self.subcon._parsereport(stream, context, path)
        if parsed != checksum:
            raise ValidationError(f'Incorrect stored checksum={parsed} - calculated={checksum}')
        return parsed

    def _build(self, checksum, stream, context, path):
        return self.subcon._build(self._get_checksum(stream), stream, context, path)
