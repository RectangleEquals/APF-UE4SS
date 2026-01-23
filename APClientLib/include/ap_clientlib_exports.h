#pragma once

#ifdef _WIN32
    #ifdef AP_CLIENTLIB_EXPORTS
        #define APCLIENT_API __declspec(dllexport)
    #else
        #define APCLIENT_API __declspec(dllimport)
    #endif
#else
    #define APCLIENT_API
#endif