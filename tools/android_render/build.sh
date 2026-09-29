#!/usr/bin/env bash
# 把 Probe.java 编译成 probe.dex。仓库里已带编好的 probe.dex，改了 Probe.java 才需要重新编译。
# 需要 JDK（javac）和 Android SDK（platforms/android-*/android.jar、build-tools/*/lib/d8.jar），
# ANDROID_HOME 指向 SDK。Termux 里没有 SDK 时，可以在装了 SDK 的 proot 容器里运行这个脚本。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
: "${ANDROID_HOME:?请把 ANDROID_HOME 设为 Android SDK 目录}"
jar=$(ls -d "$ANDROID_HOME"/platforms/android-*/android.jar | sort -V | tail -1)
d8=$(ls -d "$ANDROID_HOME"/build-tools/*/lib/d8.jar | sort -V | tail -1)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
javac --release 11 -encoding UTF-8 -cp "$jar" -d "$out" Probe.java
java -cp "$d8" com.android.tools.r8.D8 --release --min-api 26 --lib "$jar" --output "$out" "$out"/*.class
mv "$out/classes.dex" probe.dex
echo "已生成 $PWD/probe.dex（$(basename "$(dirname "$jar")")，d8 $(basename "$(dirname "$(dirname "$d8")")")）"
