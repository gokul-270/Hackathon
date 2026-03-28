
# GenerateGitVersionScript.cmake — invoked via cmake -P on every build
# Inputs (passed via -D): HEADER_TEMPLATE, TIMESTAMP_TEMPLATE,
#                          OUTPUT_HEADER, OUTPUT_TIMESTAMP_CPP, SOURCE_DIR

# 1. Generate build timestamp (local time, matches old __DATE__ __TIME__ format)
string(TIMESTAMP BUILD_TIMESTAMP "%b %d %Y %H:%M:%S")

# 2. Detect git hash and branch
set(GIT_HASH "")
set(GIT_BRANCH "")

find_program(GIT_EXECUTABLE git)

if(GIT_EXECUTABLE AND EXISTS "${SOURCE_DIR}/.git")
    # Git is available — use it directly
    execute_process(
        COMMAND ${GIT_EXECUTABLE} rev-parse --short HEAD
        WORKING_DIRECTORY "${SOURCE_DIR}"
        OUTPUT_VARIABLE GIT_HASH
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
        RESULT_VARIABLE GIT_RESULT
    )
    if(NOT GIT_RESULT EQUAL 0)
        set(GIT_HASH "")
    endif()

    execute_process(
        COMMAND ${GIT_EXECUTABLE} rev-parse --abbrev-ref HEAD
        WORKING_DIRECTORY "${SOURCE_DIR}"
        OUTPUT_VARIABLE GIT_BRANCH
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
    )

    # Check for dirty working tree
    execute_process(
        COMMAND ${GIT_EXECUTABLE} diff --quiet HEAD
        WORKING_DIRECTORY "${SOURCE_DIR}"
        RESULT_VARIABLE GIT_DIRTY_RESULT
        ERROR_QUIET
    )
    if(NOT GIT_DIRTY_RESULT EQUAL 0 AND NOT GIT_HASH STREQUAL "")
        set(GIT_HASH "${GIT_HASH}-dirty")
    endif()

elseif(EXISTS "${SOURCE_DIR}/.git_version")
    # No git, but .git_version fallback file exists (created by sync.sh)
    file(READ "${SOURCE_DIR}/.git_version" GIT_VERSION_CONTENT)
    string(STRIP "${GIT_VERSION_CONTENT}" GIT_VERSION_CONTENT)
    # Format: HASH BRANCH (space-separated on one line)
    string(REPLACE " " ";" GIT_VERSION_LIST "${GIT_VERSION_CONTENT}")
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
configure_file("${HEADER_TEMPLATE}" "${OUTPUT_HEADER}" @ONLY)

# 4. Generate the timestamp .cpp (always changes → always recompiles, but tiny)
configure_file("${TIMESTAMP_TEMPLATE}" "${OUTPUT_TIMESTAMP_CPP}" @ONLY)
