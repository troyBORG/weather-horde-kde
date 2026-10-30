#pragma once
#include <QString>
#include <sys/stat.h>
bool validTokenMetadata(const struct stat &s, uid_t uid);
QString readPrivateToken(const QString &stateRoot, QString *reason = nullptr);
