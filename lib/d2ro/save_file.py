"""
Structs that represent parts of Diablo II Remastered save files.

:author: Doug Skrypa
"""

import logging
import shutil
from pathlib import Path
from typing import Union

from construct import Struct, Bytes, Int32ul
# from construct import Int8ul, Int32sl, Float64l, Float32l, PaddedString
# from construct import Enum, FlagsEnum, Sequence, BitStruct, Flag, BitsSwapped, ExprValidator, RawCopy

# from .adapters import Checksum
from .constructed import Constructed
from .utils import unique_path

__all__ = ['CTLOFile', 'CTLOStruct']
log = logging.getLogger(__name__)


# region Save File
CTLOStruct = Struct(
    _unk0=Bytes(12),
    seed_candidate_0=Int32ul,
    _unk1=Bytes(162),
    seed_candidate_1=Int32ul,
    _unk2=Bytes(712),
)
# endregion


class CTLOFile(Constructed, construct=CTLOStruct):
    """Represents a ctlo file"""

    def __init__(self, data: bytes, path: Path = None):
        super().__init__(data)
        self._path = path

    @classmethod
    def load(cls, path: Union[str, Path]) -> 'CTLOFile':
        path = Path(path).expanduser()
        log.debug(f'Loading game data from path={path.as_posix()}')
        return cls(path.read_bytes(), path)

    def save(self, path: Union[str, Path] = None, backup: bool = True):
        """
        Save changes.

        :param path: Location where save file should be written (defaults to the path from which this save file was read
          if :meth:`.load` was used or an explicit path was provided)
        :param backup: Whether a backup copy of the original save file should be saved
        """
        path = Path(path).expanduser() if path else self._path
        if not path:
            raise ValueError(f'A path is required to save {self}')

        data = self._construct.build(self._build())  # Prevent creating an empty file if an exception is raised

        if backup and path.exists():
            bkp_path = unique_path(path.parent, path.name, '.bkp')
            log.info(f'Creating backup: {bkp_path.as_posix()}')
            shutil.copy(path, bkp_path)

        log.info(f'Saving {path.as_posix()}')
        Path(path).expanduser().write_bytes(data)
