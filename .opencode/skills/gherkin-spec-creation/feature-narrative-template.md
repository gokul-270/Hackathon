# Feature Narrative Template

Use this template to structure your feature description before generating Gherkin scenarios.

## Template

```
Feature Title:
[One clear, user-focused title describing the capability]

Description:
[1-2 sentences about what users can do with this feature]

Actors/Personas:
[Who uses this feature? List specific roles: Administrator, Team Member, Guest, etc.]

Primary Goal:
[What are users trying to accomplish with this feature?]

Key Behaviors:
[Bulleted list of main actions/outcomes users can perform]
- [Behavior 1]
- [Behavior 2]
- [Behavior 3]

Edge Cases:
[Situations that work but are special or unusual]
- [Edge case 1]
- [Edge case 2]
- [Edge case 3]

Error Scenarios:
[Failures the system must handle gracefully]
- [Error 1]
- [Error 2]
- [Error 3]

Success Metrics:
[How do we know this feature works correctly?]
- [Metric 1]
- [Metric 2]
```

## Example 1: File Export Feature

```
Feature Title: Export Configuration to JSON

Description: 
Users can export their current system configuration settings to a JSON file for backup, sharing, or migration purposes.

Actors/Personas:
- System Administrator
- Team Lead
- Support Engineer

Primary Goal:
Enable users to safely persist configuration state to a portable format.

Key Behaviors:
- User clicks "Export Configuration" button
- User selects export location on file system
- System creates JSON file with all current settings
- Success notification confirms export completed
- User can open exported file in any text editor
- File name includes timestamp for version tracking

Edge Cases:
- Configuration contains special characters (quotes, newlines, unicode)
- Export location has spaces or unusual path characters
- Configuration is very large (1000+ settings)
- User runs export multiple times rapidly
- System files are read-only (should export successfully, marked as read-only)

Error Scenarios:
- Disk is full (cannot write file)
- Selected directory does not exist
- User lacks write permissions on selected directory
- File already exists (should prompt to overwrite or choose new name)
- File system is mounted read-only
- Network path is unreachable (if exporting to network location)

Success Metrics:
- JSON file is created at specified location
- All configuration values are present in JSON
- JSON is valid and can be parsed by standard tools
- Special characters are properly escaped
- File includes export timestamp and version identifier
```

## Example 2: User Authentication Feature

```
Feature Title: Enable Two-Factor Authentication (2FA)

Description:
Users can enable an additional security layer on their account by requiring a second authentication factor via SMS or authenticator app.

Actors/Personas:
- End User
- Account Owner
- Security Administrator

Primary Goal:
Allow users to enhance account security by requiring multiple authentication methods.

Key Behaviors:
- User navigates to Security Settings
- User clicks "Enable Two-Factor Authentication"
- User selects authentication method (SMS or authenticator app)
- User receives and enters verification code
- 2FA is activated on account
- User can view backup codes
- User can disable 2FA if needed

Edge Cases:
- User has multiple devices (phone and tablet)
- User changes phone number
- User uses backup codes to restore access
- User's authentication app is lost
- User enables 2FA then immediately disables it
- SMS delivery is delayed (user retries)

Error Scenarios:
- SMS code is entered incorrectly
- SMS code expires before user enters it
- Authentication app generates incorrect code
- Phone number is unreachable
- User loses access to authenticator app
- Too many failed authentication attempts
- SMS service is temporarily unavailable

Success Metrics:
- 2FA is required on next login
- User cannot log in without valid second factor
- Backup codes work when primary method fails
- Settings page shows 2FA is enabled with method
- Disable option removes 2FA requirement
```

## Tips for Effective Narratives

**Be Specific:**
- ✅ "User enters email and clicks Login"
- ❌ "User logs in"

**Include Context:**
- ✅ "System Administrator with full permissions"
- ❌ "User"

**List All Paths:**
- ✅ "Happy path: export succeeds; Edge case: path has spaces; Error: disk full"
- ❌ "User exports file"

**Capture Real Failures:**
- ✅ "Network timeout when exporting to network path"
- ❌ "Export might fail"

**Focus on User, Not Code:**
- ✅ "User sees success message"
- ❌ "Function returns status 200"

## How to Use This Template

1. **Fill in each section completely** — Don't skip edge cases or errors
2. **Be as detailed as possible** — This narrative becomes source material for scenarios
3. **Pass to Gherkin Spec Creation skill** — Skill uses this to generate scenarios
4. **Skill will validate coverage** — Skill checks that all behaviors, edge cases, and errors are represented
5. **Review and refine** — Approve or ask for scenario adjustments
