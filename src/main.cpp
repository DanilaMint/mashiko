#include <stdio.h>
#include <string_view>

constexpr std::string_view VERSION = "0.0.1";

int main(int argc, char* argv[]) {
    printf("Hello, mashiko!");
    return 0;
}

void version() {
    printf("%s", VERSION);
}
