# GenerateGitVersion.cmake
#
# Shared cmake module for generating git_version.h + build_timestamp.cpp.
# Used by all C++ packages (yanthra_move, motor_control_ros2, cotton_detection_ros2).
#
# Usage in CMakeLists.txt:
#   set(GIT_VERSION_TEMPLATE_DIR "${PROJECT_SOURCE_DIR}/../../cmake")
#   include(${GIT_VERSION_TEMPLATE_DIR}/GenerateGitVersion.cmake)
#   setup_git_version(my_node_target)
#
# git_version.h  — GIT_HASH + GIT_BRANCH only; regenerated when they change.
# build_timestamp.cpp — tiny file exporting getBuildTimestamp(); regenerated
#                       every build but compiles in <1s, so ccache misses on
#                       this file are cheap.

function(setup_git_version TARGET_NAME)
    # Unique target name per package to avoid collisions in multi-package builds
    set(GEN_TARGET "generate_git_version_${PROJECT_NAME}")
    set(OUTPUT_HEADER "${CMAKE_CURRENT_BINARY_DIR}/git_version.h")
    set(OUTPUT_TIMESTAMP_CPP "${CMAKE_CURRENT_BINARY_DIR}/build_timestamp.cpp")
    set(HEADER_TEMPLATE "${GIT_VERSION_TEMPLATE_DIR}/git_version.h.in")
    set(TIMESTAMP_TEMPLATE "${GIT_VERSION_TEMPLATE_DIR}/build_timestamp.cpp.in")
    set(SCRIPT_FILE "${GIT_VERSION_TEMPLATE_DIR}/GenerateGitVersionScript.cmake")

    # Create the -P script that runs on every build
    file(WRITE "${SCRIPT_FILE}" "
# GenerateGitVersionScript.cmake — invoked via cmake -P on every build
# Inputs (passed via -D): HEADER_TEMPLATE, TIMESTAMP_TEMPLATE,
#                          OUTPUT_HEADER, OUTPUT_TIMESTAMP_CPP, SOURCE_DIR

# 1. Generate build timestamp (local time, matches old __DATE__ __TIME__ format)
string(TIMESTAMP BUILD_TIMESTAMP \"%b %d %Y %H:%M:%S\")

# 2. Detect git hash and branch
set(GIT_HASH \"\")
set(GIT_BRANCH \"\")

find_program(GIT_EXECUTABLE git)

if(GIT_EXECUTABLE AND EXISTS \"\${SOURCE_DIR}/.git\")
    # Git is available — use it directly
    execute_process(
        COMMAND \${GIT_EXECUTABLE} rev-parse --short HEAD
        WORKING_DIRECTORY \"\${SOURCE_DIR}\"
        OUTPUT_VARIABLE GIT_HASH
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
        RESULT_VARIABLE GIT_RESULT
    )
    if(NOT GIT_RESULT EQUAL 0)
        set(GIT_HASH \"\")
    endif()

    execute_process(
        COMMAND \${GIT_EXECUTABLE} rev-parse --abbrev-ref HEAD
        WORKING_DIRECTORY \"\${SOURCE_DIR}\"
        OUTPUT_VARIABLE GIT_BRANCH
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
    )

    # Check for dirty working tree
    execute_process(
        COMMAND \${GIT_EXECUTABLE} diff --quiet HEAD
        WORKING_DIRECTORY \"\${SOURCE_DIR}\"
        RESULT_VARIABLE GIT_DIRTY_RESULT
        ERROR_QUIET
    )
    if(NOT GIT_DIRTY_RESULT EQUAL 0 AND NOT GIT_HASH STREQUAL \"\")
        set(GIT_HASH \"\${GIT_HASH}-dirty\")
    endif()

elseif(EXISTS \"\${SOURCE_DIR}/.git_version\")
    # No git, but .git_version fallback file exists (created by sync.sh)
    file(READ \"\${SOURCE_DIR}/.git_version\" GIT_VERSION_CONTENT)
    string(STRIP \"\${GIT_VERSION_CONTENT}\" GIT_VERSION_CONTENT)
    # Format: HASH BRANCH (space-separated on one line)
    string(REPLACE \" \" \";\" GIT_VERSION_LIST \"\${GIT_VERSION_CONTENT}\")
    list(LENGTH GIT_VERSION_LIST GIT_VERSION_LEN)
    if(GIT_VERSION_LEN GREATER_EQUAL 1)
        list(GET GIT_VERSION_LIST 0 GIT_HASH)
    endif()
    if(GIT_VERSION_LEN GREATER_EQUAL 2)
        list(GET GIT_VERSION_LIST 1 GIT_BRANCH)
    endif()
endif()

# 3. Generate the header (only GIT_HASH + GIT_BRANCH — no timestamp).
#    configure_file writes only if content changed, so downstream .cpp files
#    will NOT recompile when only the timestamp changes.
configure_file(\"\${HEADER_TEMPLATE}\" \"\${OUTPUT_HEADER}\" @ONLY)

# 4. Generate the timestamp .cpp (always changes → always recompiles, but tiny)
configure_file(\"\${TIMESTAMP_TEMPLATE}\" \"\${OUTPUT_TIMESTAMP_CPP}\" @ONLY)
")

    # Repo root is two levels up from the package source dir (src/<pkg>/ -> ../../)
    # GIT_VERSION_TEMPLATE_DIR points to <repo_root>/cmake, so parent is repo root
    get_filename_component(REPO_ROOT "${GIT_VERSION_TEMPLATE_DIR}" DIRECTORY)

    # Custom target that always runs (ALL), executing the -P script
    add_custom_target(${GEN_TARGET} ALL
        COMMAND ${CMAKE_COMMAND}
            -DHEADER_TEMPLATE=${HEADER_TEMPLATE}
            -DTIMESTAMP_TEMPLATE=${TIMESTAMP_TEMPLATE}
            -DOUTPUT_HEADER=${OUTPUT_HEADER}
            -DOUTPUT_TIMESTAMP_CPP=${OUTPUT_TIMESTAMP_CPP}
            -DSOURCE_DIR=${REPO_ROOT}
            -P ${SCRIPT_FILE}
        COMMENT "Generating git_version.h for ${PROJECT_NAME}"
    )

    # Ensure the node target depends on version generation and can find the header.
    # Add the generated build_timestamp.cpp to the target's sources.
    add_dependencies(${TARGET_NAME} ${GEN_TARGET})
    target_include_directories(${TARGET_NAME} PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
    # Mark generated so CMake does not check for existence at configure time
    set_source_files_properties(${OUTPUT_TIMESTAMP_CPP} PROPERTIES GENERATED TRUE)
    target_sources(${TARGET_NAME} PRIVATE ${OUTPUT_TIMESTAMP_CPP})
endfunction()
