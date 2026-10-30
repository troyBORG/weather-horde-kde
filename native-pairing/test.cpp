#include "tokenreader.h"
#include <QCoreApplication>
#include <QTemporaryDir>
#include <QDir>
#include <QFile>
#include <cassert>
#include <cstdio>
#include <unistd.h>
#include <sys/stat.h>
int main(int argc, char **argv) {
 QCoreApplication app(argc,argv);
 QTemporaryDir temp;
 const auto state=temp.path()+"/state";
 QDir().mkpath(state+"/weather-horde-kde");
 auto path=state+"/weather-horde-kde/token";
 const auto bytes=path.toLocal8Bit();
 auto put=[&](QByteArray value) { QFile f(path); assert(f.open(QIODevice::WriteOnly|QIODevice::Truncate)); f.write(value); f.close(); chmod(bytes,0600); };
 assert(readPrivateToken(state).isEmpty());
 put(QByteArray(43,'a')); assert(readPrivateToken(state)==QString(43,'a'));
 // Reproduce the deployed 0777 ancestor, keeping token 0600 and app dir 0700.
 chmod((state+"/weather-horde-kde").toLocal8Bit(),0700);
 chmod(state.toLocal8Bit(),0777);
 QString reason;
 assert(readPrivateToken(state,&reason).isEmpty());
 assert(reason==state+": directory is group/world-writable");
 chmod(state.toLocal8Bit(),0700);
 assert(readPrivateToken(state,&reason)==QString(43,'a'));
 assert(reason.isEmpty());
 chmod(bytes,0644); assert(readPrivateToken(state).isEmpty());
 chmod(bytes,0600); chmod((state+"/weather-horde-kde").toLocal8Bit(),0777); assert(readPrivateToken(state).isEmpty());
 chmod((state+"/weather-horde-kde").toLocal8Bit(),0700);
 put("short"); assert(readPrivateToken(state).isEmpty());
 put(QByteArray(5000,'a')); assert(readPrivateToken(state).isEmpty());
 put(QByteArray(40,'a')+"\nInjected"); assert(readPrivateToken(state).isEmpty());
 put(QByteArray(43,'a'));
 assert(link(bytes,(bytes+".link").constData())==0); assert(readPrivateToken(state).isEmpty()); unlink((bytes+".link").constData());
 QFile::rename(path,path+".real"); assert(symlink((bytes+".real").constData(),bytes)==0); assert(readPrivateToken(state).isEmpty()); unlink(bytes);
 assert(mkfifo(bytes,0600)==0); assert(readPrivateToken(state).isEmpty()); unlink(bytes);
 put(QByteArray(43,'b')); assert(readPrivateToken(state)==QString(43,'b'));
 // Real foreign-owner metadata with all other fields made valid isolates UID check.
 struct stat foreign{}; assert(stat("/etc/passwd",&foreign)==0); assert(foreign.st_uid!=getuid());
 foreign.st_mode=S_IFREG|0600; foreign.st_nlink=1; foreign.st_size=43;
 assert(!validTokenMetadata(foreign,getuid()));
 assert(readPrivateToken("/etc").isEmpty());
 std::puts("PRIVATE_TOKEN_BOUNDARY_PASS: private, missing, mode, directory, owner, symlink, hardlink, FIFO, format, rotation");
}
