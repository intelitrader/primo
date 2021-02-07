#include <windows.h> /* Sleep() */

#include <stdio.h>
#include <stdlib.h>

int main(int argc, char* argv[])
{
    int sec_count = 0;
    void* first_alloc = malloc(300 * 1024 * 1024);

    while( 1 )
    {
        Sleep(1000);

        if( sec_count >= 60 )
        {
            void* leak = malloc(10 * 1024 * 1024);
        }

        if( ++sec_count == 30 )
        {
            free(first_alloc);
        }
    }
}

