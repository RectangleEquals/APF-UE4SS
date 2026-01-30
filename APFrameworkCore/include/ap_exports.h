#pragma once

#ifdef _WIN32
#ifdef AP_FRAMEWORK_EXPORTS
#define AP_API __declspec(dllexport)
#else
#define AP_API __declspec(dllimport)
#endif
#else
#define AP_API
#endif