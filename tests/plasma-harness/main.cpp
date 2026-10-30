// Real Plasma applet context, isolated XDG dirs and private D-Bus only.
#include <QApplication>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQuickWindow>
#include <QTimer>
#include <KPackage/Package>
#include <KPackage/PackageLoader>
#include <Plasma/Applet>
#include <Plasma/Corona>
#include <Plasma/Containment>
#include <Plasma/PluginLoader>
#include <PlasmaQuick/AppletQuickItem>
class TestCorona : public Plasma::Corona {
public: QRect screenGeometry(uint) const override { return QRect(0,0,460,720); }
};
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    if (argc != 3) return 2;
    QFile config(argv[1]);
    if (!config.open(QIODevice::ReadOnly)) return 3;
    const auto options = QJsonDocument::fromJson(config.readAll()).object();
    TestCorona corona;
    auto shell = KPackage::PackageLoader::self()->loadPackage("Plasma/Shell");
    shell.setPath("org.kde.plasma.desktop");
    corona.setKPackage(shell);
    auto *containment = corona.createContainment("null");
    auto *applet = containment->createApplet("org.troyborg.weatherhorde");
    if (!applet) return 4;
    auto *item = PlasmaQuick::AppletQuickItem::itemForApplet(applet);
    if (!item || item->applet() != applet) return 5;
    item->setProperty("controllerBase", options["base"].toString());
    item->setProperty("controllerToken", options["token"].toString());
    QQuickWindow window;
    window.resize(460,720);
    item->setParentItem(window.contentItem());
    item->setSize(options["desktop"].toBool() ? QSizeF(300,150) : QSizeF(440,700));
    if (!options["desktop"].toBool()) {
        item->setPreferredRepresentation(item->fullRepresentation());
        item->setExpanded(true);
    }
    window.show();
    auto *engine = qmlEngine(item);
    QQmlComponent test(engine, QUrl::fromLocalFile(argv[2]));
    auto *runner = test.createWithInitialProperties({{"widget",QVariant::fromValue(item)}});
    if (!runner) { qCritical() << test.errors(); return 6; }
    QObject::connect(engine, &QQmlEngine::quit, &app, &QApplication::quit);
    QTimer::singleShot(15000, &app, &QApplication::quit);
    qInfo("PLASMA_PACKAGE_ROOT_PASS");
    const int result = app.exec();
    if (!options["screenshot"].toString().isEmpty()) {
        if (!window.grabWindow().save(options["screenshot"].toString())) return 7;
    }
    delete runner;
    item->setParentItem(nullptr);
    return result;
}
