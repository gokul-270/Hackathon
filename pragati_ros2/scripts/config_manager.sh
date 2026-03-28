#!/usr/bin/env bash
#
# Pragati ROS2 Configuration Manager
# ===================================
# Interactive setup and management of configuration profiles
#
# Usage:
#   ./scripts/config_manager.sh           # Interactive setup
#   ./scripts/config_manager.sh --show    # Show current config
#   ./scripts/config_manager.sh --reset   # Reset to defaults
#   ./scripts/config_manager.sh --add-profile <name>  # Add new profile

set -e

# ============================================================================
# Setup
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$WORKSPACE_ROOT/config.env"
EXAMPLE_FILE="$WORKSPACE_ROOT/config.env.example"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════════════════${NC}"
}

print_section() {
    echo ""
    echo -e "${CYAN}${BOLD}$1${NC}"
    echo -e "${CYAN}$(printf '%.0s─' {1..79})${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Detect WSL
is_wsl() {
    if [ -f /proc/version ] && grep -qi microsoft /proc/version; then
        return 0
    fi
    return 1
}

# Prompt with default value
prompt_with_default() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    local value

    if [ -n "$default" ]; then
        read -p "$(echo -e "${CYAN}$prompt${NC} [${YELLOW}$default${NC}]: ")" value
        value="${value:-$default}"
    else
        read -p "$(echo -e "${CYAN}$prompt${NC}: ")" value
    fi

    eval "$var_name='$value'"
}

# Validate IP address
validate_ip() {
    local ip="$1"
    if [[ $ip =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        return 0
    fi
    return 1
}

# Test SSH connection
test_ssh_connection() {
    local user="$1"
    local ip="$2"
    local ssh_key="$3"

    local ssh_cmd="ssh"
    if [ -n "$ssh_key" ]; then
        ssh_cmd="ssh -i $ssh_key"
    fi

    echo -e "${YELLOW}Testing SSH connection to $user@$ip...${NC}"
    if timeout 5 $ssh_cmd -o BatchMode=yes -o ConnectTimeout=5 "$user@$ip" "echo 'SSH OK'" &>/dev/null; then
        print_success "SSH connection successful!"
        return 0
    else
        print_warning "SSH connection failed (this is OK if device is offline)"
        return 1
    fi
}

# ============================================================================
# Configuration Functions
# ============================================================================

show_current_config() {
    print_header "Current Configuration"

    if [ ! -f "$CONFIG_FILE" ]; then
        print_warning "No configuration file found at: $CONFIG_FILE"
        echo -e "${YELLOW}Run without --show to create a new configuration${NC}"
        return 1
    fi

    echo -e "${BOLD}Configuration file:${NC} $CONFIG_FILE"
    echo ""

    # Source the config
    source "$CONFIG_FILE"

    print_section "Default Target"
    echo -e "  IP Address:    ${CYAN}${RPI_IP:-<not set>}${NC}"
    echo -e "  Username:      ${CYAN}${RPI_USER:-ubuntu}${NC}"
    echo -e "  Target Dir:    ${CYAN}${RPI_TARGET_DIR:-~/pragati_ros2}${NC}"
    echo -e "  SSH Key:       ${CYAN}${RPI_SSH_KEY:-<default>}${NC}"

    print_section "Cross-Compilation"
    echo -e "  Sysroot Path:  ${CYAN}${RPI_SYSROOT:-<not set>}${NC}"
    echo -e "  Build Packages: ${CYAN}${BUILD_PACKAGES:-<all>}${NC}"

    # Show profiles
    if [ -n "$ALL_PROFILES" ]; then
        print_section "Configured Profiles"
        IFS=',' read -ra PROFILES <<< "$ALL_PROFILES"
        for profile in "${PROFILES[@]}"; do
            profile=$(echo "$profile" | xargs)  # Trim whitespace
            profile_upper=$(echo "$profile" | tr '[:lower:]' '[:upper:]')

            # Get profile variables
            ip_var="${profile_upper}_IP"
            user_var="${profile_upper}_USER"
            dir_var="${profile_upper}_TARGET_DIR"
            key_var="${profile_upper}_SSH_KEY"

            echo ""
            echo -e "  ${BOLD}${CYAN}Profile: $profile${NC}"
            echo -e "    IP:         ${!ip_var:-<not set>}"
            echo -e "    User:       ${!user_var:-ubuntu}"
            echo -e "    Target Dir: ${!dir_var:-~/pragati_ros2}"
            echo -e "    SSH Key:    ${!key_var:-<default>}"
        done
    else
        print_section "Profiles"
        echo -e "  ${YELLOW}No profiles configured${NC}"
    fi

    echo ""
    print_info "Edit $CONFIG_FILE to make changes"
    print_info "Or run: ./scripts/config_manager.sh --add-profile <name>"
}

reset_config() {
    print_header "Reset Configuration"

    if [ -f "$CONFIG_FILE" ]; then
        echo -e "${YELLOW}Current config will be backed up to: ${CONFIG_FILE}.backup${NC}"
        read -p "$(echo -e "${RED}Are you sure you want to reset? [y/N]:${NC} ")" confirm

        if [[ ! $confirm =~ ^[Yy]$ ]]; then
            echo "Reset cancelled"
            return 1
        fi

        cp "$CONFIG_FILE" "${CONFIG_FILE}.backup"
        print_success "Backup created: ${CONFIG_FILE}.backup"
    fi

    if [ -f "$EXAMPLE_FILE" ]; then
        cp "$EXAMPLE_FILE" "$CONFIG_FILE"
        print_success "Configuration reset from example file"
    else
        print_error "Example file not found: $EXAMPLE_FILE"
        return 1
    fi
}

# ============================================================================
# Interactive Setup
# ============================================================================

interactive_setup() {
    print_header "Pragati ROS2 - Interactive Configuration"

    echo ""
    echo -e "${BOLD}This wizard will help you configure your build and deployment environment.${NC}"
    echo -e "Press ${CYAN}Enter${NC} to accept default values shown in ${YELLOW}[brackets]${NC}."
    echo ""

    # Check if config already exists
    if [ -f "$CONFIG_FILE" ]; then
        print_warning "Configuration file already exists: $CONFIG_FILE"
        read -p "$(echo -e "${YELLOW}Do you want to reconfigure? [y/N]:${NC} ")" reconfigure

        if [[ ! $reconfigure =~ ^[Yy]$ ]]; then
            echo "Setup cancelled. Current configuration preserved."
            return 0
        fi

        # Backup existing config
        cp "$CONFIG_FILE" "${CONFIG_FILE}.backup"
        print_success "Existing config backed up to: ${CONFIG_FILE}.backup"
    fi

    # Initialize from example
    if [ -f "$EXAMPLE_FILE" ]; then
        cp "$EXAMPLE_FILE" "$CONFIG_FILE"
    else
        print_error "Example configuration not found: $EXAMPLE_FILE"
        return 1
    fi

    # ========================================================================
    # Default Target Configuration
    # ========================================================================

    print_section "1. Default Target Configuration"
    echo "Configure the primary Raspberry Pi target for deployment."
    echo ""

    # Detect platform and suggest sysroot
    DEFAULT_SYSROOT="$HOME/rpi-sysroot"
    if is_wsl; then
        print_info "WSL detected - suggested sysroot: $DEFAULT_SYSROOT"
    else
        print_info "Native Linux detected - suggested sysroot: $DEFAULT_SYSROOT"
    fi

    # Get IP address
    while true; do
        prompt_with_default "Target IP address" "192.168.137.253" RPI_IP
        if validate_ip "$RPI_IP"; then
            break
        else
            print_error "Invalid IP address format"
        fi
    done

    # Get username
    prompt_with_default "SSH username" "ubuntu" RPI_USER

    # Get target directory
    prompt_with_default "Target directory on RPi" "~/pragati_ros2" RPI_TARGET_DIR

    # SSH key (optional)
    read -p "$(echo -e "${CYAN}SSH key path (optional, press Enter to use default):${NC} ")" RPI_SSH_KEY

    # Test connection
    echo ""
    read -p "$(echo -e "${CYAN}Test SSH connection now? [Y/n]:${NC} ")" test_conn
    if [[ ! $test_conn =~ ^[Nn]$ ]]; then
        test_ssh_connection "$RPI_USER" "$RPI_IP" "$RPI_SSH_KEY"
    fi

    # ========================================================================
    # Cross-Compilation Settings
    # ========================================================================

    print_section "2. Cross-Compilation Settings"
    echo "Configure the sysroot path for cross-compiling to ARM."
    echo ""

    prompt_with_default "Sysroot path" "$DEFAULT_SYSROOT" RPI_SYSROOT

    # Check if sysroot exists
    if [ -d "$RPI_SYSROOT" ]; then
        print_success "Sysroot directory found: $RPI_SYSROOT"
    else
        print_warning "Sysroot directory not found: $RPI_SYSROOT"
        print_info "You'll need to set this up before cross-compiling"
        print_info "See: docs/CROSS_COMPILATION_GUIDE.md"
    fi

    # Build packages
    echo ""
    read -p "$(echo -e "${CYAN}Default packages to build (space-separated, or Enter for all):${NC} ")" BUILD_PACKAGES

    # ========================================================================
    # Additional Profiles
    # ========================================================================

    print_section "3. Additional Profiles (Optional)"
    echo "You can configure multiple RPi targets (e.g., rpi1, rpi2, vehicle1)."
    echo ""

    read -p "$(echo -e "${CYAN}Add additional profiles now? [y/N]:${NC} ")" add_profiles

    PROFILES=()
    if [[ $add_profiles =~ ^[Yy]$ ]]; then
        while true; do
            echo ""
            read -p "$(echo -e "${CYAN}Profile name (e.g., rpi1, vehicle1) or Enter to finish:${NC} ")" profile_name

            if [ -z "$profile_name" ]; then
                break
            fi

            # Validate profile name (alphanumeric + underscore)
            if [[ ! $profile_name =~ ^[a-zA-Z0-9_]+$ ]]; then
                print_error "Invalid profile name. Use only letters, numbers, and underscores."
                continue
            fi

            PROFILES+=("$profile_name")

            profile_upper=$(echo "$profile_name" | tr '[:lower:]' '[:upper:]')

            echo -e "${BOLD}Configuring profile: $profile_name${NC}"

            # Get profile settings
            while true; do
                prompt_with_default "  IP address" "" profile_ip
                if validate_ip "$profile_ip"; then
                    eval "${profile_upper}_IP='$profile_ip'"
                    break
                else
                    print_error "Invalid IP address"
                fi
            done

            prompt_with_default "  Username" "ubuntu" profile_user
            eval "${profile_upper}_USER='$profile_user'"

            prompt_with_default "  Target directory" "~/pragati_ros2" profile_dir
            eval "${profile_upper}_TARGET_DIR='$profile_dir'"

            read -p "$(echo -e "${CYAN}  SSH key (optional):${NC} ")" profile_key
            if [ -n "$profile_key" ]; then
                eval "${profile_upper}_SSH_KEY='$profile_key'"
            fi

            print_success "Profile '$profile_name' configured"
        done
    fi

    # ========================================================================
    # Write Configuration
    # ========================================================================

    print_section "4. Saving Configuration"

    # Build the config file
    cat > "$CONFIG_FILE" << EOF
# Pragati ROS2 Configuration
# Generated by config_manager.sh on $(date)
# Edit this file or re-run: ./scripts/config_manager.sh

# ============================================================================
# Default Target Configuration
# ============================================================================

RPI_IP=$RPI_IP
RPI_USER=$RPI_USER
RPI_TARGET_DIR=$RPI_TARGET_DIR
EOF

    if [ -n "$RPI_SSH_KEY" ]; then
        echo "RPI_SSH_KEY=$RPI_SSH_KEY" >> "$CONFIG_FILE"
    fi

    cat >> "$CONFIG_FILE" << EOF

# ============================================================================
# Cross-Compilation Settings
# ============================================================================

RPI_SYSROOT=$RPI_SYSROOT
EOF

    if [ -n "$BUILD_PACKAGES" ]; then
        echo "BUILD_PACKAGES=\"$BUILD_PACKAGES\"" >> "$CONFIG_FILE"
    fi

    # Add profiles if any
    if [ ${#PROFILES[@]} -gt 0 ]; then
        cat >> "$CONFIG_FILE" << EOF

# ============================================================================
# Named Profiles
# ============================================================================

EOF

        for profile in "${PROFILES[@]}"; do
            profile_upper=$(echo "$profile" | tr '[:lower:]' '[:upper:]')

            echo "# Profile: $profile" >> "$CONFIG_FILE"
            echo "${profile_upper}_IP=${!profile_upper}_IP" >> "$CONFIG_FILE"
            echo "${profile_upper}_USER=${!profile_upper}_USER" >> "$CONFIG_FILE"
            echo "${profile_upper}_TARGET_DIR=${!profile_upper}_TARGET_DIR" >> "$CONFIG_FILE"

            key_var="${profile_upper}_SSH_KEY"
            if [ -n "${!key_var}" ]; then
                echo "${profile_upper}_SSH_KEY=${!key_var}" >> "$CONFIG_FILE"
            fi

            echo "" >> "$CONFIG_FILE"
        done

        # Add ALL_PROFILES list
        ALL_PROFILES_STR=$(IFS=','; echo "${PROFILES[*]}")
        echo "ALL_PROFILES=\"$ALL_PROFILES_STR\"" >> "$CONFIG_FILE"
    fi

    print_success "Configuration saved to: $CONFIG_FILE"

    # ========================================================================
    # Summary
    # ========================================================================

    print_section "Setup Complete!"

    echo ""
    echo -e "${BOLD}Configuration Summary:${NC}"
    echo -e "  Default Target: ${CYAN}$RPI_USER@$RPI_IP${NC}"
    echo -e "  Sysroot:        ${CYAN}$RPI_SYSROOT${NC}"

    if [ ${#PROFILES[@]} -gt 0 ]; then
        echo -e "  Profiles:       ${CYAN}${#PROFILES[@]} configured${NC}"
    fi

    echo ""
    echo -e "${BOLD}Next Steps:${NC}"
    echo -e "  1. ${CYAN}./build.sh rpi -p motor_control_ros2${NC}  # Cross-compile"
    echo -e "  2. ${CYAN}./sync.sh${NC}                             # Deploy to default target"

    if [ ${#PROFILES[@]} -gt 0 ]; then
        echo -e "  3. ${CYAN}./sync.sh --profile ${PROFILES[0]}${NC}            # Deploy to specific profile"
    fi

    echo ""
    print_info "View config:  ./scripts/config_manager.sh --show"
    print_info "Add profile:  ./scripts/config_manager.sh --add-profile <name>"
    print_info "Edit config:  nano $CONFIG_FILE"

    echo ""
}

add_profile() {
    local profile_name="$1"

    if [ -z "$profile_name" ]; then
        print_error "Profile name required"
        echo "Usage: $0 --add-profile <name>"
        return 1
    fi

    # Validate profile name
    if [[ ! $profile_name =~ ^[a-zA-Z0-9_]+$ ]]; then
        print_error "Invalid profile name. Use only letters, numbers, and underscores."
        return 1
    fi

    if [ ! -f "$CONFIG_FILE" ]; then
        print_error "Configuration file not found: $CONFIG_FILE"
        print_info "Run: ./scripts/config_manager.sh to create initial configuration"
        return 1
    fi

    print_header "Add New Profile: $profile_name"

    profile_upper=$(echo "$profile_name" | tr '[:lower:]' '[:upper:]')

    # Get profile settings
    while true; do
        prompt_with_default "IP address" "" profile_ip
        if validate_ip "$profile_ip"; then
            break
        else
            print_error "Invalid IP address"
        fi
    done

    prompt_with_default "Username" "ubuntu" profile_user
    prompt_with_default "Target directory" "~/pragati_ros2" profile_dir
    read -p "$(echo -e "${CYAN}SSH key (optional):${NC} ")" profile_key

    # Test connection
    echo ""
    read -p "$(echo -e "${CYAN}Test SSH connection now? [Y/n]:${NC} ")" test_conn
    if [[ ! $test_conn =~ ^[Nn]$ ]]; then
        test_ssh_connection "$profile_user" "$profile_ip" "$profile_key"
    fi

    # Append to config file
    echo "" >> "$CONFIG_FILE"
    echo "# Profile: $profile_name (added $(date +%Y-%m-%d))" >> "$CONFIG_FILE"
    echo "${profile_upper}_IP=$profile_ip" >> "$CONFIG_FILE"
    echo "${profile_upper}_USER=$profile_user" >> "$CONFIG_FILE"
    echo "${profile_upper}_TARGET_DIR=$profile_dir" >> "$CONFIG_FILE"

    if [ -n "$profile_key" ]; then
        echo "${profile_upper}_SSH_KEY=$profile_key" >> "$CONFIG_FILE"
    fi

    # Update ALL_PROFILES
    source "$CONFIG_FILE"
    if [ -n "$ALL_PROFILES" ]; then
        sed -i "s/ALL_PROFILES=\".*\"/ALL_PROFILES=\"$ALL_PROFILES,$profile_name\"/" "$CONFIG_FILE"
    else
        echo "" >> "$CONFIG_FILE"
        echo "ALL_PROFILES=\"$profile_name\"" >> "$CONFIG_FILE"
    fi

    print_success "Profile '$profile_name' added to configuration"
    echo ""
    print_info "Use with: ./sync.sh --profile $profile_name"
}

# ============================================================================
# Main
# ============================================================================

main() {
    case "${1:-}" in
        --show)
            show_current_config
            ;;
        --reset)
            reset_config
            ;;
        --add-profile)
            add_profile "$2"
            ;;
        --help|-h)
            echo "Pragati ROS2 Configuration Manager"
            echo ""
            echo "Usage:"
            echo "  $0                      Interactive setup"
            echo "  $0 --show               Show current configuration"
            echo "  $0 --reset              Reset to defaults"
            echo "  $0 --add-profile <name> Add new profile"
            echo "  $0 --help               Show this help"
            ;;
        *)
            interactive_setup
            ;;
    esac
}

main "$@"
