FROM mcr.microsoft.com/azure-sql-edge:latest

USER root

# Add sqlcmd from go-sqlcmd (supports linux/arm64 natively) without this sqlserver in mac dsnt pass the sqlcmd
WORKDIR /opt/mssql-tools/bin
ENV GOSQLCMD_VERSION=v1.5.0
ARG TARGETPLATFORM
RUN case ${TARGETPLATFORM} in \
    "linux/amd64")  GOSQLCMD_ARCH=amd64 ;; \
    "linux/arm64")  GOSQLCMD_ARCH=arm64 ;; \
    *) echo "Unsupported platform: ${TARGETPLATFORM}"; exit 1 ;; \
    esac \
 && wget -q https://github.com/microsoft/go-sqlcmd/releases/download/${GOSQLCMD_VERSION}/sqlcmd-${GOSQLCMD_VERSION}-linux-${GOSQLCMD_ARCH}.tar.bz2 \
 && tar -xjf sqlcmd-${GOSQLCMD_VERSION}-linux-${GOSQLCMD_ARCH}.tar.bz2 \
 && rm sqlcmd-${GOSQLCMD_VERSION}-linux-${GOSQLCMD_ARCH}.tar.bz2

WORKDIR /
