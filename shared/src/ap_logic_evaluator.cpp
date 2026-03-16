#include "ap_logic_evaluator.h"
#include "ap_logger.h"

#include <algorithm>
#include <cctype>
#include <sstream>
#include <stdexcept>
#include <tuple>
#include <utility>

namespace ap {

// =============================================================================
// Factory Helpers
// =============================================================================

LogicNode LogicNode::make_const(bool value)
{
    LogicNode n;
    n.type = LogicNodeType::Const;
    n.const_value = value;
    return n;
}

LogicNode LogicNode::make_item(const std::string &name, int count)
{
    LogicNode n;
    n.type = LogicNodeType::Item;
    n.item_name = name;
    n.item_count = count;
    return n;
}

LogicNode LogicNode::make_can_access(const std::string &region)
{
    LogicNode n;
    n.type = LogicNodeType::CanAccess;
    n.region = region;
    return n;
}

LogicNode LogicNode::make_option(const std::string &name, const std::string &op,
                                  const std::string &value)
{
    LogicNode n;
    n.type = LogicNodeType::Option;
    n.option_name = name;
    n.option_op = op;
    n.option_value = value;
    return n;
}

LogicNode LogicNode::make_and(std::vector<LogicNode> children)
{
    LogicNode n;
    n.type = LogicNodeType::And;
    n.children = std::move(children);
    return n;
}

LogicNode LogicNode::make_or(std::vector<LogicNode> children)
{
    LogicNode n;
    n.type = LogicNodeType::Or;
    n.children = std::move(children);
    return n;
}

// =============================================================================
// Tokenizer
// =============================================================================

namespace {

enum class TokenType
{
    Item,
    CanAccess,
    Option,
    And,
    Or,
    True,
    False,
    LParen,
    RParen
};

struct Token
{
    TokenType type;
    // Item: (name, count)
    std::string str_val;
    int int_val = 1;
    // Option: (name, op, value)
    std::string opt_op;
    std::string opt_value;
};

std::string trim(const std::string &s)
{
    size_t start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos)
        return "";
    size_t end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

std::vector<Token> tokenize(const std::string &logic)
{
    std::vector<Token> tokens;
    size_t i = 0;
    size_t n = logic.size();

    while (i < n)
    {
        // Skip whitespace
        if (std::isspace(static_cast<unsigned char>(logic[i])))
        {
            ++i;
            continue;
        }

        // Parenthesized expressions
        if (logic[i] == '(')
        {
            auto rest = logic.substr(i);

            // (Item: NAME) or (Item: NAME : COUNT)
            if (rest.rfind("(Item:", 0) == 0)
            {
                i += 6; // skip "(Item:"
                auto close = logic.find(')', i);
                if (close == std::string::npos)
                    throw std::runtime_error("Unclosed '(Item:' near position " + std::to_string(i));

                std::string content = trim(logic.substr(i, close - i));
                Token tok;
                tok.type = TokenType::Item;

                // Split on last ':' for optional count
                auto colon = content.rfind(':');
                if (colon != std::string::npos)
                {
                    std::string after = trim(content.substr(colon + 1));
                    bool all_digits = !after.empty();
                    for (char c : after)
                    {
                        if (!std::isdigit(static_cast<unsigned char>(c)))
                        {
                            all_digits = false;
                            break;
                        }
                    }
                    if (all_digits)
                    {
                        tok.str_val = trim(content.substr(0, colon));
                        tok.int_val = std::stoi(after);
                    }
                    else
                    {
                        tok.str_val = content;
                        tok.int_val = 1;
                    }
                }
                else
                {
                    tok.str_val = content;
                    tok.int_val = 1;
                }

                tokens.push_back(tok);
                i = close + 1;
                continue;
            }

            // (Can Access: REGION)
            if (rest.rfind("(Can Access:", 0) == 0)
            {
                i += 12; // skip "(Can Access:"
                auto close = logic.find(')', i);
                if (close == std::string::npos)
                    throw std::runtime_error("Unclosed '(Can Access:' near position " + std::to_string(i));

                Token tok;
                tok.type = TokenType::CanAccess;
                tok.str_val = trim(logic.substr(i, close - i));
                tokens.push_back(tok);
                i = close + 1;
                continue;
            }

            // (Goal: NAME) — syntactic sugar for (Option: goal == NAME)
            // Special reserved values:
            //   (Goal: none) → goal option is empty string (no goal selected / default mode)
            //   (Goal: ?)    → boolean truthy check (any goal is active)
            if (rest.rfind("(Goal:", 0) == 0)
            {
                i += 6; // skip "(Goal:"
                auto close = logic.find(')', i);
                if (close == std::string::npos)
                    throw std::runtime_error("Unclosed '(Goal:' near position " + std::to_string(i));

                std::string goal_name = trim(logic.substr(i, close - i));
                Token tok;
                tok.type = TokenType::Option;
                tok.str_val = "goal";

                std::string lower_name = goal_name;
                std::transform(lower_name.begin(), lower_name.end(), lower_name.begin(),
                               [](unsigned char c){ return std::tolower(c); });

                if (goal_name == "?")
                {
                    tok.opt_op = "";    // boolean check: truthy when any goal is set
                    tok.opt_value = "";
                }
                else if (lower_name == "none")
                {
                    tok.opt_op = "==";  // match empty string = no goal selected
                    tok.opt_value = "";
                }
                else
                {
                    tok.opt_op = "==";
                    tok.opt_value = goal_name;
                }

                tokens.push_back(tok);
                i = close + 1;
                continue;
            }

            // (Option: NAME) or (Option: NAME OP VALUE)
            if (rest.rfind("(Option:", 0) == 0)
            {
                i += 8; // skip "(Option:"
                auto close = logic.find(')', i);
                if (close == std::string::npos)
                    throw std::runtime_error("Unclosed '(Option:' near position " + std::to_string(i));

                std::string content = trim(logic.substr(i, close - i));
                Token tok;
                tok.type = TokenType::Option;

                // Try to match "NAME OP VALUE" pattern
                // Operators: >=, <=, !=, ==, >, <
                static const std::vector<std::string> ops = {">=", "<=", "!=", "==", ">", "<"};
                bool found_op = false;

                for (const auto &op : ops)
                {
                    auto pos = content.find(op);
                    if (pos != std::string::npos)
                    {
                        tok.str_val = trim(content.substr(0, pos));
                        tok.opt_op = op;
                        tok.opt_value = trim(content.substr(pos + op.size()));
                        found_op = true;
                        break;
                    }
                }

                if (!found_op)
                {
                    tok.str_val = content;
                    tok.opt_op = "";
                    tok.opt_value = "";
                }

                tokens.push_back(tok);
                i = close + 1;
                continue;
            }

            // Plain grouping paren
            Token tok;
            tok.type = TokenType::LParen;
            tokens.push_back(tok);
            ++i;
            continue;
        }

        if (logic[i] == ')')
        {
            Token tok;
            tok.type = TokenType::RParen;
            tokens.push_back(tok);
            ++i;
            continue;
        }

        // Keywords — must be followed by non-alnum or end
        auto remaining = logic.substr(i);

        if (remaining.rfind("AND", 0) == 0 && (remaining.size() == 3 || !std::isalnum(static_cast<unsigned char>(remaining[3]))))
        {
            Token tok;
            tok.type = TokenType::And;
            tokens.push_back(tok);
            i += 3;
            continue;
        }

        if (remaining.rfind("OR", 0) == 0 && (remaining.size() == 2 || !std::isalnum(static_cast<unsigned char>(remaining[2]))))
        {
            Token tok;
            tok.type = TokenType::Or;
            tokens.push_back(tok);
            i += 2;
            continue;
        }

        if (remaining.rfind("True", 0) == 0 && (remaining.size() == 4 || !std::isalnum(static_cast<unsigned char>(remaining[4]))))
        {
            Token tok;
            tok.type = TokenType::True;
            tokens.push_back(tok);
            i += 4;
            continue;
        }

        if (remaining.rfind("False", 0) == 0 && (remaining.size() == 5 || !std::isalnum(static_cast<unsigned char>(remaining[5]))))
        {
            Token tok;
            tok.type = TokenType::False;
            tokens.push_back(tok);
            i += 5;
            continue;
        }

        throw std::runtime_error(
            "Unexpected character at position " + std::to_string(i) + ": '" +
            std::string(1, logic[i]) + "' in expression: " + logic);
    }

    return tokens;
}

// =============================================================================
// Recursive Descent Parser
// =============================================================================

class Parser
{
  public:
    explicit Parser(std::vector<Token> tokens) : tokens_(std::move(tokens)) {}

    LogicNode parse()
    {
        if (tokens_.empty())
            return LogicNode::make_const(true);

        auto result = parse_expression();

        if (pos_ < tokens_.size())
            throw std::runtime_error("Unexpected token after expression at position " + std::to_string(pos_));

        return result;
    }

  private:
    std::vector<Token> tokens_;
    size_t pos_ = 0;

    const Token *peek()
    {
        if (pos_ < tokens_.size())
            return &tokens_[pos_];
        return nullptr;
    }

    Token consume()
    {
        if (pos_ >= tokens_.size())
            throw std::runtime_error("Unexpected end of expression");
        return tokens_[pos_++];
    }

    void expect(TokenType type)
    {
        auto tok = consume();
        if (tok.type != type)
            throw std::runtime_error("Expected token type " + std::to_string(static_cast<int>(type)));
    }

    // expression := and_expr ('OR' and_expr)*
    LogicNode parse_expression()
    {
        std::vector<LogicNode> parts;
        parts.push_back(parse_and_expr());

        while (peek() && peek()->type == TokenType::Or)
        {
            consume(); // eat OR
            parts.push_back(parse_and_expr());
        }

        if (parts.size() == 1)
            return std::move(parts[0]);
        return LogicNode::make_or(std::move(parts));
    }

    // and_expr := primary ('AND' primary)*
    LogicNode parse_and_expr()
    {
        std::vector<LogicNode> parts;
        parts.push_back(parse_primary());

        while (peek() && peek()->type == TokenType::And)
        {
            consume(); // eat AND
            parts.push_back(parse_primary());
        }

        if (parts.size() == 1)
            return std::move(parts[0]);
        return LogicNode::make_and(std::move(parts));
    }

    // primary := leaf | '(' expression ')'
    LogicNode parse_primary()
    {
        auto *tok = peek();
        if (!tok)
            throw std::runtime_error("Unexpected end of expression");

        switch (tok->type)
        {
        case TokenType::Item: {
            auto t = consume();
            return LogicNode::make_item(t.str_val, t.int_val);
        }
        case TokenType::CanAccess: {
            auto t = consume();
            return LogicNode::make_can_access(t.str_val);
        }
        case TokenType::Option: {
            auto t = consume();
            return LogicNode::make_option(t.str_val, t.opt_op, t.opt_value);
        }
        case TokenType::True:
            consume();
            return LogicNode::make_const(true);
        case TokenType::False:
            consume();
            return LogicNode::make_const(false);
        case TokenType::LParen: {
            consume(); // eat (
            auto expr = parse_expression();
            expect(TokenType::RParen);
            return expr;
        }
        default:
            throw std::runtime_error("Unexpected token in primary");
        }
    }
};

} // anonymous namespace

// =============================================================================
// Public Parser API
// =============================================================================

LogicNode parse_logic(const std::string &logic)
{
    // Empty/whitespace -> always accessible
    bool all_space = true;
    for (char c : logic)
    {
        if (!std::isspace(static_cast<unsigned char>(c)))
        {
            all_space = false;
            break;
        }
    }
    if (logic.empty() || all_space)
        return LogicNode::make_const(true);

    auto tokens = tokenize(logic);
    return Parser(std::move(tokens)).parse();
}

// =============================================================================
// Option Evaluation
// =============================================================================

LogicNode evaluate_options(const LogicNode &node, const std::map<std::string, std::string> &options)
{
    switch (node.type)
    {
    case LogicNodeType::Option: {
        auto it = options.find(node.option_name);
        if (it == options.end())
        {
            // Unknown option — include by default (permissive)
            APLogger::get()->log(LogLevel::Warn, "APLogicEval",
                "Unknown option '" + node.option_name + "' in logic — defaulting to true (permissive)");
            return LogicNode::make_const(true);
        }

        const std::string &value_str = it->second;

        if (node.option_op.empty())
        {
            // Boolean check — truthy if non-empty, non-zero, non-false
            bool truthy = !value_str.empty() && value_str != "0" && value_str != "false" && value_str != "False";
            return LogicNode::make_const(truthy);
        }

        // Comparison — try numeric first, fall back to string
        bool result = false;
        try
        {
            double left = std::stod(value_str);
            double right = std::stod(node.option_value);

            if (node.option_op == ">=")
                result = left >= right;
            else if (node.option_op == "<=")
                result = left <= right;
            else if (node.option_op == ">")
                result = left > right;
            else if (node.option_op == "<")
                result = left < right;
            else if (node.option_op == "==")
                result = left == right;
            else if (node.option_op == "!=")
                result = left != right;
        }
        catch (...)
        {
            // String comparison fallback — lowercase both sides for case-insensitive match
            // (mirrors Python's evaluate_options which applies .lower() to both operands)
            std::string left_lower = value_str;
            std::string right_lower = node.option_value;
            std::transform(left_lower.begin(), left_lower.end(), left_lower.begin(),
                           [](unsigned char c){ return std::tolower(c); });
            std::transform(right_lower.begin(), right_lower.end(), right_lower.begin(),
                           [](unsigned char c){ return std::tolower(c); });
            if (node.option_op == "==")
                result = left_lower == right_lower;
            else if (node.option_op == "!=")
                result = left_lower != right_lower;
            else if (node.option_op == ">=")
                result = left_lower >= right_lower;
            else if (node.option_op == "<=")
                result = left_lower <= right_lower;
            else if (node.option_op == ">")
                result = left_lower > right_lower;
            else if (node.option_op == "<")
                result = left_lower < right_lower;
        }

        return LogicNode::make_const(result);
    }

    case LogicNodeType::And: {
        std::vector<LogicNode> children;
        children.reserve(node.children.size());
        for (const auto &child : node.children)
            children.push_back(evaluate_options(child, options));
        return LogicNode::make_and(std::move(children));
    }

    case LogicNodeType::Or: {
        std::vector<LogicNode> children;
        children.reserve(node.children.size());
        for (const auto &child : node.children)
            children.push_back(evaluate_options(child, options));
        return LogicNode::make_or(std::move(children));
    }

    default:
        // Item, CanAccess, Const — unchanged
        return node;
    }
}

// =============================================================================
// Simplification
// =============================================================================

LogicNode simplify(const LogicNode &node)
{
    switch (node.type)
    {
    case LogicNodeType::And: {
        std::vector<LogicNode> children;
        for (const auto &child : node.children)
        {
            children.push_back(simplify(child));
        }

        // AND with any False -> False
        for (const auto &c : children)
        {
            if (c.type == LogicNodeType::Const && !c.const_value)
                return LogicNode::make_const(false);
        }

        // Remove True children
        std::vector<LogicNode> filtered;
        for (auto &c : children)
        {
            if (!(c.type == LogicNodeType::Const && c.const_value))
                filtered.push_back(std::move(c));
        }

        if (filtered.empty())
            return LogicNode::make_const(true);
        if (filtered.size() == 1)
            return std::move(filtered[0]);
        return LogicNode::make_and(std::move(filtered));
    }

    case LogicNodeType::Or: {
        std::vector<LogicNode> children;
        for (const auto &child : node.children)
        {
            children.push_back(simplify(child));
        }

        // OR with any True -> True
        for (const auto &c : children)
        {
            if (c.type == LogicNodeType::Const && c.const_value)
                return LogicNode::make_const(true);
        }

        // Remove False children
        std::vector<LogicNode> filtered;
        for (auto &c : children)
        {
            if (!(c.type == LogicNodeType::Const && !c.const_value))
                filtered.push_back(std::move(c));
        }

        if (filtered.empty())
            return LogicNode::make_const(false);
        if (filtered.size() == 1)
            return std::move(filtered[0]);
        return LogicNode::make_or(std::move(filtered));
    }

    default:
        return node;
    }
}

// =============================================================================
// Display String Generation
// =============================================================================

std::string logic_node_to_display(const LogicNode &node)
{
    switch (node.type)
    {
    case LogicNodeType::Const:
        return node.const_value ? "True" : "False";

    case LogicNodeType::Item:
        if (node.item_count > 1)
            return "(Item: " + node.item_name + " : " + std::to_string(node.item_count) + ")";
        return "(Item: " + node.item_name + ")";

    case LogicNodeType::CanAccess:
        return "(Can Access: " + node.region + ")";

    case LogicNodeType::Option:
        if (node.option_op.empty())
            return "(Option: " + node.option_name + ")";
        return "(Option: " + node.option_name + " " + node.option_op + " " + node.option_value + ")";

    case LogicNodeType::And: {
        std::string result;
        for (size_t i = 0; i < node.children.size(); ++i)
        {
            if (i > 0)
                result += " AND ";
            result += logic_node_to_display(node.children[i]);
        }
        return result;
    }

    case LogicNodeType::Or: {
        std::string result;
        for (size_t i = 0; i < node.children.size(); ++i)
        {
            if (i > 0)
                result += " OR ";
            // Wrap AND children in parens for clarity
            if (node.children[i].type == LogicNodeType::And)
                result += "(" + logic_node_to_display(node.children[i]) + ")";
            else
                result += logic_node_to_display(node.children[i]);
        }
        return result;
    }
    }

    return "???";
}

// =============================================================================
// Scored Evaluation
// =============================================================================

ScoredNode evaluate_scored(const LogicNode &node, const TrackerState &state)
{
    ScoredNode scored;
    scored.type = node.type;
    scored.display = logic_node_to_display(node);

    switch (node.type)
    {
    case LogicNodeType::Const:
        scored.score = node.const_value ? 1.0f : 0.0f;
        break;

    case LogicNodeType::Item: {
        auto it = state.received_items.find(node.item_name);
        int have = (it != state.received_items.end()) ? it->second : 0;
        if (node.item_count <= 0)
            scored.score = 1.0f;
        else
            scored.score = std::min(static_cast<float>(have) / static_cast<float>(node.item_count), 1.0f);
        break;
    }

    case LogicNodeType::CanAccess:
        scored.score = state.reachable_regions.count(node.region) ? 1.0f : 0.0f;
        break;

    case LogicNodeType::Option:
        // Options should be resolved before scoring; treat unresolved as true
        scored.score = 1.0f;
        break;

    case LogicNodeType::And: {
        float sum = 0.0f;
        for (const auto &child : node.children)
        {
            auto child_scored = evaluate_scored(child, state);
            sum += child_scored.score;
            scored.children.push_back(std::move(child_scored));
        }
        scored.score = node.children.empty() ? 1.0f : sum / static_cast<float>(node.children.size());
        break;
    }

    case LogicNodeType::Or: {
        float max_score = 0.0f;
        for (const auto &child : node.children)
        {
            auto child_scored = evaluate_scored(child, state);
            max_score = std::max(max_score, child_scored.score);
            scored.children.push_back(std::move(child_scored));
        }
        scored.score = max_score;
        break;
    }
    }

    return scored;
}

float evaluate_score(const LogicNode &node, const TrackerState &state)
{
    return evaluate_scored(node, state).score;
}

bool evaluate_bool(const LogicNode &node, const TrackerState &state)
{
    return evaluate_score(node, state) >= 1.0f;
}

// =============================================================================
// Region Graph — Fixed-Point Reachability
// =============================================================================

std::set<std::string> compute_reachable_regions(
    const std::vector<RegionInfo> &regions,
    const TrackerState &state)
{
    // Start with Menu always reachable + initial reachable set
    std::set<std::string> reachable = state.reachable_regions;
    reachable.insert("Menu");

    // Also include regions with no logic (always reachable)
    for (const auto &region : regions)
    {
        if (region.access_logic.type == LogicNodeType::Const && region.access_logic.const_value)
        {
            reachable.insert(region.name);
        }
    }

    // Fixed-point iteration
    bool changed = true;
    int pass = 0;
    while (changed)
    {
        changed = false;
        pass++;
        int newly_reachable = 0;

        for (const auto &region : regions)
        {
            if (reachable.count(region.name))
                continue; // Already reachable

            // Build state with current reachable set for evaluation
            TrackerState eval_state;
            eval_state.received_items = state.received_items;
            eval_state.reachable_regions = reachable;

            if (evaluate_bool(region.access_logic, eval_state))
            {
                reachable.insert(region.name);
                changed = true;
                newly_reachable++;
            }
        }

        APLogger::get()->log(LogLevel::Debug, "APLogicEval",
                             "Reachability pass " + std::to_string(pass) +
                                 ": +" + std::to_string(newly_reachable) +
                                 " new (" + std::to_string(reachable.size()) +
                                 "/" + std::to_string(regions.size()) + " total reachable)");
    }

    return reachable;
}

} // namespace ap
