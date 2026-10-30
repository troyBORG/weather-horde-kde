#pragma once
#include <QObject>
#include <QStandardPaths>
#include <QtQml/qqmlregistration.h>
#include "tokenreader.h"
class LocalPairing : public QObject {
 Q_OBJECT
 QML_ELEMENT
 Q_PROPERTY(QString diagnostic READ diagnostic NOTIFY diagnosticChanged)
public:
 explicit LocalPairing(QObject *parent=nullptr):QObject(parent){}
 QString diagnostic() const { return m_diagnostic; }
 // Fixed basename; no arbitrary file accessor or token property.
 Q_INVOKABLE QString readToken() {
   QString reason;
   auto token=readPrivateToken(QStandardPaths::writableLocation(QStandardPaths::GenericStateLocation), &reason);
   if(reason!=m_diagnostic) { m_diagnostic=reason; emit diagnosticChanged(); }
   return token;
 }
signals:
 void diagnosticChanged();
private:
 QString m_diagnostic;
};
