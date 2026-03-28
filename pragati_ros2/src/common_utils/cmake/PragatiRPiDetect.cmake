# PragatiRPiDetect.cmake — Detect Raspberry Pi (aarch64/arm) target architecture.
#
# Usage: After find_package(common_utils REQUIRED), call include(PragatiRPiDetect).
#        (Automatically included by PragatiDefaults.cmake.)
#
# Sets:
#   PRAGATI_IS_RPI  — TRUE on aarch64/arm (RPi 4B), FALSE otherwise.
#
# Consumers can use: if(PRAGATI_IS_RPI) for conditional compilation.

# Idempotent guard
if(_PRAGATI_RPI_DETECT_INCLUDED)
  return()
endif()
set(_PRAGATI_RPI_DETECT_INCLUDED TRUE)

if(CMAKE_SYSTEM_PROCESSOR MATCHES "arm" OR CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64")
  set(PRAGATI_IS_RPI TRUE)
else()
  set(PRAGATI_IS_RPI FALSE)
endif()
