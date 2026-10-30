#include "tokenreader.h"
#include <QRegularExpression>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
namespace {
struct Fd { int fd; explicit Fd(int n):fd(n){} ~Fd(){if(fd>=0) close(fd);} };
QString directoryError(int fd, bool privateOwner) {
 struct stat s{};
 if(fd<0) return errno==ENOENT ? "directory missing" : "directory inaccessible or symlink rejected";
 if(fstat(fd,&s)!=0 || !S_ISDIR(s.st_mode)) return "directory metadata unavailable";
 if((privateOwner && s.st_uid!=getuid()) || (s.st_uid!=getuid() && s.st_uid!=0)) return "directory owner is not trusted";
 if((s.st_mode & 0022) && !(s.st_uid==0 && (s.st_mode&S_ISVTX))) return "directory is group/world-writable";
 return {};
}
}
bool validTokenMetadata(const struct stat &s, uid_t uid) {
 return S_ISREG(s.st_mode) && s.st_uid==uid && (s.st_mode&07777)==0600
     && s.st_nlink==1 && s.st_size>=32 && s.st_size<=256;
}
QString readPrivateToken(const QString &stateRoot, QString *reason) {
 if(reason) reason->clear();
 auto fail=[&](const QString &message)->QString { if(reason) *reason=message; return {}; };
 if(!stateRoot.startsWith('/') || getuid()!=geteuid()) return fail("invalid state path or user identity");
 Fd dir(open("/",O_RDONLY|O_DIRECTORY|O_CLOEXEC));
 const auto parts=stateRoot.split('/',Qt::SkipEmptyParts);
 QString path;
 for(const auto &part:parts) {
   if(part==".." || part==".") return fail("state path traversal rejected");
   path += "/"+part;
   int next=openat(dir.fd,part.toLocal8Bit(),O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
   // Capture errno before closing the previous descriptor.
   const auto error=directoryError(next,false);
   close(dir.fd); dir.fd=next;
   if(!error.isEmpty()) return fail(path+": "+error);
 }
 auto error=directoryError(dir.fd,true);
 if(!error.isEmpty()) return fail(stateRoot+": "+error);
 Fd state(openat(dir.fd,"weather-horde-kde",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC));
 error=directoryError(state.fd,true);
 if(!error.isEmpty()) return fail(stateRoot+"/weather-horde-kde: "+error);
 Fd file(openat(state.fd,"token",O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC));
 if(file.fd<0) return fail(errno==ENOENT ? "private token file missing" : "private token inaccessible or symlink rejected");
 struct stat before{},after{};
 if(fstat(file.fd,&before)!=0) return fail("private token metadata unavailable");
 if(!validTokenMetadata(before,getuid())) return fail("private token rejected: requires same-user regular single-link file, mode 0600, size 32–256 bytes");
 char buffer[257]; const auto size=read(file.fd,buffer,sizeof(buffer));
 if(size!=before.st_size || fstat(file.fd,&after)!=0 || !validTokenMetadata(after,getuid())
    || before.st_size!=after.st_size || before.st_mtim.tv_sec!=after.st_mtim.tv_sec
    || before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec) return fail("private token changed during read; retrying");
 const auto value=QString::fromLatin1(buffer,size);
 static const QRegularExpression format(QStringLiteral("^[A-Za-z0-9_-]{32,256}$"));
 if(!format.match(value).hasMatch()) return fail("private token format rejected");
 return value;
}
