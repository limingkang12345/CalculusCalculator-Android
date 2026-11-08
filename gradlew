#!/bin/sh

#
#   Copyright 2015 the original author or authors.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#

# Gradle start up script for POSIX generated with the Gradle Wrapper Plugin.
# 说明：首次在 Android Studio 中打开本项目时，会自动下载 Gradle 8.9 并生成
# gradle-wrapper.jar，此后即可使用 ./gradlew 命令。

app_path=$0
APP_BASE_NAME=${0##*/}
APP_HOME=$( cd "${app_path%"${app_path##*/}"}" && pwd -P ) || exit
CLASSPATH=$APP_HOME/gradle/wrapper/gradle-wrapper.jar

cygwin=false
msys=false
darwin=false
nonstop=false
case "$( uname )" in
  CYGWIN* ) cygwin=true ;;
  Darwin* ) darwin=true ;;
  MSYS* | MINGW* ) msys=true ;;
  NONSTOP* ) nonstop=true ;;
esac

if [ -n "$JAVA_HOME" ] ; then
    if [ -x "$JAVA_HOME/jre/sh/java" ] ; then
        JAVACMD=$JAVA_HOME/jre/sh/java
    else
        JAVACMD=$JAVA_HOME/bin/java
    fi
    if [ ! -x "$JAVACMD" ] ; then
        die "ERROR: JAVA_HOME is set to an invalid directory: $JAVA_HOME"
    fi
else
    JAVACMD=java
    which java >/dev/null 2>&1 || die "ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH."
fi

MAX_FD=maximum
warn () { echo "$*" >&2; }
die () { echo; echo "$*"; echo; exit 1; } >&2
if ! "$cygwin" && ! "$darwin" && ! "$nonstop" ; then
    case $MAX_FD in
      max*) MAX_FD=$( ulimit -H -n ) || warn "Could not query maximum file descriptor limit" ;;
    esac
    case $MAX_FD in
      '' | soft) : ;;
      *) ulimit -n "$MAX_FD" || warn "Could not set maximum file descriptor limit to $MAX_FD" ;;
    esac
fi

set -- \
        "-Dorg.gradle.appname=$APP_BASE_NAME" \
        -classpath "$CLASSPATH" \
        org.gradle.wrapper.GradleWrapperMain \
        "$@"

exec "$JAVACMD" "$@"
