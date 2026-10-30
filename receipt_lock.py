"""Cooperative owner process exclusion, on the existing state directory inode.

Controller holds shared lock for its whole lifetime; receipt helper needs an
exclusive lock AND checks old/non-cooperating controllers are stopped. Never
unlink/replace the state directory while either process is running.
"""
from contextlib import contextmanager
import fcntl
import os
import stat

@contextmanager
def state_lock(root, *, exclusive):
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        if st.st_uid!=os.getuid() or st.st_mode & 0o022:
            raise ValueError('Unsafe state directory; permissions unchanged')
        fcntl.flock(fd,(fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)
