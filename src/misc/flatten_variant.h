// AI-Generated

#ifndef FLATTEN_VARIANT_H
#define FLATTEN_VARIANT_H

#include <variant>
#include <string>

// Шаг 1: Базовый инструмент, который умеет сливать два std::variant в один плоский
template <typename T, typename U>
struct variant_cat;

template <typename... Ts, typename... Us>
struct variant_cat<std::variant<Ts...>, std::variant<Us...>> {
    using type = std::variant<Ts..., Us...>;
};

// Шаг 2: Метафункция, которая проверяет, является ли тип вариантом.
// Если да — оставляет как есть, если нет — заворачивает в std::variant<T>
template <typename T>
struct ensure_variant { using type = std::variant<T>; };

template <typename... Ts>
struct ensure_variant<std::variant<Ts...>> { using type = std::variant<Ts...>; };


// Шаг 3: Финальный упаковщик, который берет список и последовательно все склеивает
template <typename... Ts>
struct flatten_variant;

// Если тип один, просто нормализуем его
template <typename T>
struct flatten_variant<T> {
    using type = typename ensure_variant<T>::type;
};

// Если типов много, сглаживаем первый, сглаживаем остальные и склеиваем их через variant_cat
template <typename T, typename... Ts>
struct flatten_variant<T, Ts...> {
    using type = typename variant_cat<
        typename ensure_variant<T>::type,
        typename flatten_variant<Ts...>::type
    >::type;
};

// Удобный алиас для использования
template <typename... Ts>
using flatten_variant_t = typename flatten_variant<Ts...>::type;

#endif
