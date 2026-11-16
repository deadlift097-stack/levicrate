cmake_minimum_required(VERSION 3.22)
project(levicrate LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# ---- mod metadata: from a converted workspace (levicrate.json) or -D overrides -------------------
set(CRATE_WORKSPACE "" CACHE PATH "Workspace made by `levicrate.py convert`")
set(MOD_ID "levicrate_demo" CACHE STRING "Package directory name")
set(MOD_NAME "Levicrate Demo" CACHE STRING "Display name")
set(MOD_AUTHOR "you" CACHE STRING "Author")
set(MOD_VERSION "0.1.0" CACHE STRING "Version")
set(MOD_LIBRARY_NAME "levicrate_demo" CACHE STRING "Library name without lib prefix / .so suffix")
set(MOD_MINECRAFT_VERSIONS "[\"1.21.*\"]" CACHE STRING "Raw JSON array for minecraft_versions")
set(MOD_ICON "" CACHE STRING "Package-relative icon path (relative to the workspace)")
set(CRATE_ASSETS_DIR "" CACHE PATH "Assets directory to include in the package")

if(NOT CRATE_WORKSPACE STREQUAL "")
  get_filename_component(CRATE_WORKSPACE "${CRATE_WORKSPACE}" ABSOLUTE)
  file(READ "${CRATE_WORKSPACE}/levicrate.json" _ws)
  string(JSON MOD_ID GET "${_ws}" id)
  string(JSON MOD_NAME GET "${_ws}" name)
  string(JSON MOD_AUTHOR GET "${_ws}" author)
  string(JSON MOD_VERSION GET "${_ws}" version)
  string(JSON MOD_LIBRARY_NAME GET "${_ws}" library)
  string(JSON MOD_MINECRAFT_VERSIONS GET "${_ws}" minecraft_versions)
  string(JSON MOD_ICON GET "${_ws}" icon)
  if(IS_DIRECTORY "${CRATE_WORKSPACE}/assets")
    set(CRATE_ASSETS_DIR "${CRATE_WORKSPACE}/assets")
  endif()
endif()
# MOD_NAME / MOD_AUTHOR end up inside JSON strings
string(REPLACE "\\" "\\\\" MOD_NAME "${MOD_NAME}")
string(REPLACE "\"" "\\\"" MOD_NAME "${MOD_NAME}")
string(REPLACE "\\" "\\\\" MOD_AUTHOR "${MOD_AUTHOR}")
string(REPLACE "\"" "\\\"" MOD_AUTHOR "${MOD_AUTHOR}")

# ---- host build: unit tests for the menu core only ---------------------------------------------
if(NOT ANDROID)
  enable_testing()
  add_executable(menu_test native/tests/menu_test.cpp)
  target_include_directories(menu_test PRIVATE native/include)
  add_test(NAME menu_test COMMAND menu_test)
  return()
endif()

# ---- Android build ------------------------------------------------------------------------------
if(NOT CMAKE_ANDROID_ARCH_ABI STREQUAL "arm64-v8a" AND NOT CMAKE_ANDROID_ARCH_ABI STREQUAL "armeabi-v7a")
  message(FATAL_ERROR "Unsupported Android ABI: ${CMAKE_ANDROID_ARCH_ABI}")
endif()

# Same SDK release the LeviLauncher template pins. A mod built against a different SDK layout can
# crash inside pl::modmenu::registerModule(), so keep this tag in sync with the launcher you target.
set(CRATE_SDK_TAG "0.2.2" CACHE STRING "preloader-android release tag")
include(FetchContent)
FetchContent_Declare(preloader_android
  GIT_REPOSITORY https://github.com/LiteLDev/preloader-android.git
  GIT_TAG ${CRATE_SDK_TAG}
  SOURCE_SUBDIR cmake/preloader-sdk)
FetchContent_MakeAvailable(preloader_android)
set(CRATE_SDK_INCLUDE "${preloader_android_SOURCE_DIR}/include")

option(CRATE_PL_MENU "Use the real pl::modmenu backend (OFF = log-only fallback)" ON)
option(CRATE_LINK_PRELOADER "Link the preloader target instead of leaving SDK symbols for runtime lookup" ON)
if(CRATE_LINK_PRELOADER AND NOT TARGET preloader)
  add_subdirectory("${preloader_android_SOURCE_DIR}" "${CMAKE_BINARY_DIR}/_preloader_android")
endif()

set(CRATE_SOURCES native/src/main.cpp native/src/CrateMod.cpp)
if(NOT CRATE_WORKSPACE STREQUAL "" AND EXISTS "${CRATE_WORKSPACE}/src/ModPort.cpp")
  list(APPEND CRATE_SOURCES "${CRATE_WORKSPACE}/src/ModPort.cpp")
  if(EXISTS "${CRATE_WORKSPACE}/src/Translated.cpp")
    list(APPEND CRATE_SOURCES "${CRATE_WORKSPACE}/src/Translated.cpp")
  endif()
  set(CRATE_HAS_PORT 1)
else()
  set(CRATE_HAS_PORT 0)
endif()

add_library(${MOD_LIBRARY_NAME} SHARED ${CRATE_SOURCES})
target_include_directories(${MOD_LIBRARY_NAME} PRIVATE native/include native/src "${CRATE_SDK_INCLUDE}")
if(CRATE_HAS_PORT)
  target_include_directories(${MOD_LIBRARY_NAME} PRIVATE "${CRATE_WORKSPACE}/src")
endif()
target_compile_definitions(${MOD_LIBRARY_NAME} PRIVATE
  LEVICRATE_PL_MENU=$<BOOL:${CRATE_PL_MENU}> LEVICRATE_HAS_PORT=${CRATE_HAS_PORT})
target_compile_options(${MOD_LIBRARY_NAME} PRIVATE -fvisibility=hidden -fvisibility-inlines-hidden)
target_link_options(${MOD_LIBRARY_NAME} PRIVATE "-Wl,-z,max-page-size=16384")

find_library(log-lib log REQUIRED)
target_link_libraries(${MOD_LIBRARY_NAME} PRIVATE ${log-lib})
if(TARGET preloader)
  target_link_libraries(${MOD_LIBRARY_NAME} PRIVATE preloader)
else()
  target_link_options(${MOD_LIBRARY_NAME} PRIVATE "-Wl,--unresolved-symbols=ignore-all")
endif()
if(CMAKE_STRIP)
  add_custom_command(TARGET ${MOD_LIBRARY_NAME} POST_BUILD
    COMMAND "${CMAKE_STRIP}" --strip-unneeded "$<TARGET_FILE:${MOD_LIBRARY_NAME}>" VERBATIM)
endif()

# ---- .levipack: zip with <MOD_ID>/{manifest.json, lib<name>.so, icon, assets/} ----------------------
configure_file("${CMAKE_CURRENT_SOURCE_DIR}/manifest.json.in" "${CMAKE_CURRENT_BINARY_DIR}/manifest.json" @ONLY)
set(PKG_ROOT "${CMAKE_CURRENT_BINARY_DIR}/package")
set(PKG_DIR "${PKG_ROOT}/${MOD_ID}")
set(PKG_FILE "${CMAKE_CURRENT_BINARY_DIR}/${MOD_ID}-${MOD_VERSION}-${CMAKE_ANDROID_ARCH_ABI}.levipack")

set(PKG_EXTRA)
if(NOT MOD_ICON STREQUAL "")
  if(IS_ABSOLUTE "${MOD_ICON}" OR MOD_ICON MATCHES "(^|/)\\.\\.(/|$)")
    message(FATAL_ERROR "MOD_ICON must be a relative path without ..")
  endif()
  get_filename_component(_icon_dir "${MOD_ICON}" DIRECTORY)
  set(_icon_src "${CRATE_WORKSPACE}/${MOD_ICON}")
  if(NOT EXISTS "${_icon_src}")
    message(FATAL_ERROR "icon not found: ${_icon_src}")
  endif()
  list(APPEND PKG_EXTRA COMMAND "${CMAKE_COMMAND}" -E make_directory "${PKG_DIR}/${_icon_dir}"
       COMMAND "${CMAKE_COMMAND}" -E copy "${_icon_src}" "${PKG_DIR}/${MOD_ICON}")
endif()
if(NOT CRATE_ASSETS_DIR STREQUAL "")
  list(APPEND PKG_EXTRA COMMAND "${CMAKE_COMMAND}" -E copy_directory "${CRATE_ASSETS_DIR}" "${PKG_DIR}/assets")
endif()

add_custom_target(levi_package
  COMMAND "${CMAKE_COMMAND}" -E rm -rf "${PKG_ROOT}"
  COMMAND "${CMAKE_COMMAND}" -E make_directory "${PKG_DIR}"
  COMMAND "${CMAKE_COMMAND}" -E copy "$<TARGET_FILE:${MOD_LIBRARY_NAME}>" "${PKG_DIR}/lib${MOD_LIBRARY_NAME}.so"
  COMMAND "${CMAKE_COMMAND}" -E copy "${CMAKE_CURRENT_BINARY_DIR}/manifest.json" "${PKG_DIR}/manifest.json"
  ${PKG_EXTRA}
  COMMAND "${CMAKE_COMMAND}" -E chdir "${PKG_ROOT}" "${CMAKE_COMMAND}" -E tar cf "${PKG_FILE}" --format=zip "${MOD_ID}"
  DEPENDS ${MOD_LIBRARY_NAME}
  COMMENT "Packaging ${MOD_ID} -> ${PKG_FILE}"
  VERBATIM)
