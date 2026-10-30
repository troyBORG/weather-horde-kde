// Reproduce Plasma Applet::readConfig's actual KConfig QVariant contract.
// Isolated temporary config only; no session bus or real wallpaper access.
#include <QCoreApplication>
#include <QTemporaryDir>
#include <QDebug>
#include <KConfig>
#include <KConfigGroup>
int main(int argc,char **argv){
 QCoreApplication app(argc,argv);QTemporaryDir dir;
 KConfig config(dir.path()+"/fixture",KConfig::SimpleConfig);
 KConfigGroup group(&config,"General");
 group.writeEntry("FillMode",QVariant(1));
 auto untyped=group.readEntry("FillMode",QVariant(QString()));
 auto typed=group.readEntry("FillMode",QVariant(2));
 qInfo()<<"readConfig without default:"<<untyped<<"typed:"<<typed;
 return untyped.metaType().id()==QMetaType::QString && typed.metaType().id()==QMetaType::Int ? 0:1;
}
