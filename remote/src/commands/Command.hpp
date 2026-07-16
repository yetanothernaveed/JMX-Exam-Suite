#pragma once
#include "../lib/CLI11.hpp" // For command-line parsing
#include "../lib/json.hpp" // We'll use this for packaging

class Command {
public:
    virtual ~Command() = default;
    
    // Register the subcommand and its specific options to CLI11
    virtual void setup(CLI::App& app) = 0;
    
    // Check if this specific subcommand was executed by the user
    virtual bool is_called() const = 0;
    
    // Package the command data into a JSON object for the daemon
    virtual nlohmann::json serialize() const = 0;
};
