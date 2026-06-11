#ifndef NODE_H
#define NODE_H

/// Redirect
#include "../../misc/flatten_variant.h"
#include "../../misc/pos.h"

#include <optional>
#include <memory>
#include <vector>
#include <variant>

template<typename T>
class Node {
    private:
    T inner;
    Span span;

    public:
    Node(T inner, Span span): inner(inner), span(span) {}

    Span getSpan() { return this->span; }

    const T* getInnerConstPtr() { return this->inner; }

    T* getInnerPtr() { return this->inner; }

    std::unique_ptr<Node<T>> intoBox() { return std::make_unique(this); }

    std::optional<Node<T>> intoOptional() { return std::make_optional(this); }

    std::optional<std::unique_ptr<Node<T>>> intoOptionalBox() { return std::make_optional(std::make_unique(this)); }
};

/// Alias to `std::unique_ptr<Node<T>>`
template<typename T> using BoxedNode = std::unique_ptr<Node<T>>;

/// Alias to `std::optional<Node<T>>`
template<typename T> using OptionalNode = std::optional<Node<T>>;

/// Alias to `std::optional<std::unique_ptr<Node<T>>>`
template<typename T> using OptionalBoxedNode = std::optional<std::unique_ptr<Node<T>>>;

/// Alias to `std::optional<Node<T>>`
template<typename T> using NodeList = std::vector<Node<T>>;

#endif
