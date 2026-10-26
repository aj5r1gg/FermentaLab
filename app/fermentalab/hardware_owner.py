"""
FermentaLab simulated hardware-owner process exclusion.

Provides Linux advisory process locking for cooperating
controller processes.

A stable parent-directory lock prevents replacement of the
lock-file pathname from creating an independent ownership
domain among cooperating controllers.

This module does not operate GPIO, relays, mains equipment
or physical actuators.

Process exclusion alone is not hardware-command fencing,
watchdog permission or physical safety qualification.
"""

import fcntl
import os
import stat
from pathlib import Path


class HardwareOwnershipError(RuntimeError):
    """Exclusive controller ownership could not be established."""


class HardwareOwner:
    """
    Hold exclusive Linux advisory locks for one controller.

    Lock order:
        1. Parent directory.
        2. Ownership lock file.

    Both locks remain held until explicit release or process
    termination.

    All cooperating controllers must use the same canonical
    ownership directory and lock-file pathname.
    """

    def __init__(self, lock_path):
        self.lock_path = Path(lock_path).resolve()
        self._directory_fd = None
        self._fd = None

    @property
    def acquired(self):
        return (
            self._directory_fd is not None
            and self._fd is not None
        )

    def acquire(self):
        if self._directory_fd is not None or self._fd is not None:
            raise HardwareOwnershipError(
                "Hardware ownership already acquired"
            )

        directory_fd = None
        fd = None

        try:
            directory_fd = os.open(
                self.lock_path.parent,
                os.O_RDONLY
                | os.O_DIRECTORY
                | os.O_CLOEXEC,
            )

            fcntl.flock(
                directory_fd,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )

            fd = os.open(
                self.lock_path,
                os.O_RDWR
                | os.O_CREAT
                | os.O_NOFOLLOW
                | os.O_CLOEXEC,
                0o600,
            )

            fcntl.flock(
                fd,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )

            descriptor_stat = os.fstat(fd)
            pathname_stat = os.lstat(self.lock_path)

            if not stat.S_ISREG(descriptor_stat.st_mode):
                raise HardwareOwnershipError(
                    "Ownership lock is not a regular file"
                )

            if descriptor_stat.st_nlink != 1:
                raise HardwareOwnershipError(
                    "Ownership lock has invalid link count"
                )

            if (
                descriptor_stat.st_dev != pathname_stat.st_dev
                or descriptor_stat.st_ino != pathname_stat.st_ino
            ):
                raise HardwareOwnershipError(
                    "Ownership lock pathname changed"
                )

            self._directory_fd = directory_fd
            self._fd = fd

        except (OSError, HardwareOwnershipError) as exc:
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)

            if directory_fd is not None:
                try:
                    fcntl.flock(
                        directory_fd,
                        fcntl.LOCK_UN,
                    )
                finally:
                    os.close(directory_fd)

            if isinstance(exc, HardwareOwnershipError):
                raise

            raise HardwareOwnershipError(
                "Hardware ownership unavailable"
            ) from exc

    def valid(self):
        """
        Check whether the acquired ownership pathnames still
        identify the locked filesystem objects.

        This is a point-in-time integrity check, not an
        independent hardware safety guarantee.
        """
        if not self.acquired:
            return False

        try:
            directory_fd_stat = os.fstat(self._directory_fd)
            directory_path_stat = os.lstat(
                self.lock_path.parent
            )

            file_fd_stat = os.fstat(self._fd)
            file_path_stat = os.lstat(self.lock_path)

            if not stat.S_ISDIR(directory_fd_stat.st_mode):
                return False

            if not stat.S_ISDIR(directory_path_stat.st_mode):
                return False

            if not stat.S_ISREG(file_fd_stat.st_mode):
                return False

            if not stat.S_ISREG(file_path_stat.st_mode):
                return False

            if file_fd_stat.st_nlink != 1:
                return False

            if (
                directory_fd_stat.st_dev
                != directory_path_stat.st_dev
                or directory_fd_stat.st_ino
                != directory_path_stat.st_ino
            ):
                return False

            if (
                file_fd_stat.st_dev != file_path_stat.st_dev
                or file_fd_stat.st_ino != file_path_stat.st_ino
            ):
                return False

            return True

        except OSError:
            return False

    def release(self):
        fd = self._fd
        directory_fd = self._directory_fd

        self._fd = None
        self._directory_fd = None

        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

        if directory_fd is not None:
            try:
                fcntl.flock(
                    directory_fd,
                    fcntl.LOCK_UN,
                )
            finally:
                os.close(directory_fd)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()
