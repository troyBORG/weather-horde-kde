cmake_minimum_required(VERSION 3.20)
project(weather_pairing LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 REQUIRED COMPONENTS Core Qml)
qt_policy(SET QTP0001 NEW)
qt_add_qml_module(weatherpairing URI WeatherHorde.LocalPairing VERSION 1.0
    OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../plasma-widget/org.troyborg.weatherhorde/contents/ui/WeatherHorde/LocalPairing"
    SOURCES localpairing.h tokenreader.h tokenreader.cpp)
target_link_libraries(weatherpairing PRIVATE Qt6::Core)
set_target_properties(weatherpairing weatherpairingplugin PROPERTIES
 LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../plasma-widget/org.troyborg.weatherhorde/contents/ui/WeatherHorde/LocalPairing"
 BUILD_WITH_INSTALL_RPATH TRUE INSTALL_RPATH "$ORIGIN")
add_executable(pairing-test test.cpp tokenreader.cpp)
target_link_libraries(pairing-test PRIVATE Qt6::Core)
# Assertions remain active even when a release build is requested.
target_compile_options(pairing-test PRIVATE -UNDEBUG)
