# Pinned official image and signed, dated package repository; no rolling -Syu.
FROM archlinux:base@sha256:e82623936fa1a69700b48e98b058df6eaab18b737c27473a7234a40fdecb9413
RUN printf 'Server = https://archive.archlinux.org/repos/2026/11/01/$repo/os/$arch\n' > /etc/pacman.d/mirrorlist \
    && pacman -Syyuu --noconfirm --needed base-devel cmake extra-cmake-modules git \
       python python-pillow python-yaml nodejs qt6-base qt6-declarative \
       libplasma kpackage plasma-workspace dbus systemd \
    && pacman -Scc --noconfirm \
    && useradd --create-home --uid 1001 ci \
    && chmod 700 /home/ci
USER ci
WORKDIR /home/ci
ENV HOME=/home/ci PYTHONDONTWRITEBYTECODE=1
