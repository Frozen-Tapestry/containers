# ---------- Stage 1: builder ----------
FROM ghcr.io/frozen-tapestry/minideb:bookworm AS builder

ARG TARGETARCH
ENV OS_ARCH="${TARGETARCH:-amd64}" \
    OS_FLAVOUR="debian-12" \
    OS_NAME="linux" \
    OPENLDAP_VERSION="2.6.13" \
    OPENLDAP_SHA256="d693b49517a42efb85a1a364a310aed16a53d428d1b46c0d31ef3fba78fcb656"

# Build prerequisites
RUN install_packages \
      ca-certificates curl file \
      build-essential autoconf automake libtool pkg-config m4 flex bison \
      libssl-dev libsasl2-dev libltdl-dev libevent-dev libargon2-dev libperl-dev \
      unixodbc-dev libwiredtiger-dev libnsl-dev zlib1g-dev groff-base \
      libcrypt-dev \
      heimdal-dev

WORKDIR /src

# Fetch and unpack OpenLDAP source
RUN curl -fsSL -o openldap.tgz \
      "https://www.openldap.org/software/download/OpenLDAP/openldap-release/openldap-${OPENLDAP_VERSION}.tgz" \
 && echo "${OPENLDAP_SHA256} openldap.tgz" | sha256sum -c - \
 && tar -xzf openldap.tgz \
 && rm -f openldap.tgz

WORKDIR /src/openldap-${OPENLDAP_VERSION}

# Configure & build
ENV LDFLAGS="-Wl,-rpath,/opt/bitnami/openldap/lib"
RUN ./configure \
      --prefix=/opt/bitnami/openldap \
      --sysconfdir=/opt/bitnami/openldap/etc \
      --localstatedir=/opt/bitnami/openldap/var \
      --libexecdir=/opt/bitnami/openldap/lib \
      --sbindir=/opt/bitnami/openldap/sbin \
      --with-subdir=. \
      --with-tls=openssl \
      --enable-slapd \
      --enable-crypt \
      --enable-dynamic \
      --enable-modules \
      --enable-overlays=mod \
      --enable-backends=mod \
      --enable-mdb=yes \
 && make -j"$(nproc)" \
 && make install

RUN set -eux; \
      export MAKEFLAGS="-j$(nproc)"; \
      CT_PREFIX_ARGS="prefix=/opt/bitnami/openldap exec_prefix=/opt/bitnami/openldap libexecdir=/opt/bitnami/openldap/libexec"; \
      for d in \
          contrib/slapd-modules/autogroup \
          contrib/slapd-modules/lastbind \
          contrib/slapd-modules/passwd/pbkdf2 \
          contrib/slapd-modules/passwd/sha2 \
      ; do \
        make -C "$d" ${MAKEFLAGS} ${CT_PREFIX_ARGS}; \
        make -C "$d" install ${CT_PREFIX_ARGS} mandir=/opt/bitnami/openldap/share/man; \
      done; \
      HEIMDAL_INC="-I/usr/include/heimdal"; \
      HEIMDAL_LIB="-L/usr/lib/x86_64-linux-gnu"; \
      for d in \
        contrib/slapd-modules/smbk5pwd \
      ; do \
        make -C "$d" ${MAKEFLAGS} ${CT_PREFIX_ARGS} HEIMDAL_INC="$HEIMDAL_INC" HEIMDAL_LIB="$HEIMDAL_LIB"; \
        make -C "$d" install ${CT_PREFIX_ARGS} mandir=/opt/bitnami/openldap/share/man HEIMDAL_INC="$HEIMDAL_INC" HEIMDAL_LIB="$HEIMDAL_LIB"; \
      done; \
      strip -s /opt/bitnami/openldap/sbin/* 2>/dev/null || true; \
      strip -s /opt/bitnami/openldap/libexec/openldap/* 2>/dev/null || true; \
      strip -s /opt/bitnami/openldap/lib/openldap/* 2>/dev/null || true

# ---------- Stage 2: final ----------
FROM ghcr.io/frozen-tapestry/minideb:bookworm

ARG TARGETARCH

ENV APP_VERSION="2.6.13" \
    BITNAMI_APP_NAME="openldap" \
    IMAGE_REVISION="6" \
    PATH="/opt/bitnami/openldap/bin:/opt/bitnami/openldap/sbin:/opt/bitnami/openldap/lib:$PATH"

LABEL org.opencontainers.image.title="openldap" \
      org.opencontainers.image.description="Application packaged by Frozen Tapestry." \
      org.opencontainers.image.vendor="Frozen Tapestry" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.source="https://github.com/frozen-tapestry/containers/tree/prime/openldap"

ENV HOME="/" \
    OS_ARCH="${TARGETARCH:-amd64}" \
    OS_FLAVOUR="debian-12" \
    OS_NAME="linux"

COPY prebuildfs /

# Install required system packages and dependencies
RUN install_packages ca-certificates libargon2-1 libcap2-bin libcom-err2 libcrypt1 libgssapi-krb5-2 libk5crypto3 libkeyutils1 libkrb5-3 libkrb5support0 libltdl7 libnsl2 libnss3-tools libodbc2 libperl5.36 libsasl2-2 libssl3 libtirpc3 libwrap0 mdbtools procps psmisc

COPY --from=builder --chown=1001:0 /opt/bitnami /opt/bitnami

RUN find /usr /opt /bin /sbin -xdev -type f -perm /6000 -exec chmod a-s {} + || true

COPY rootfs /
RUN /opt/bitnami/scripts/openldap/postunpack.sh
ENV APP_VERSION="2.6.13" \
    BITNAMI_APP_NAME="openldap" \
    IMAGE_REVISION="0" \
    PATH="/opt/bitnami/openldap/bin:/opt/bitnami/openldap/sbin:$PATH"

EXPOSE 1389 1636

USER 1001
ENTRYPOINT [ "/opt/bitnami/scripts/openldap/entrypoint.sh" ]
CMD [ "/opt/bitnami/scripts/openldap/run.sh" ]
