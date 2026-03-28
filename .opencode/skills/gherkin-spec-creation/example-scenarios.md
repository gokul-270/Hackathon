# Gherkin Example Scenarios

Reference examples of well-written Gherkin scenarios. Study these before generating your own.

## Example 1: File Export Feature

### Feature Narrative

```
Feature Title: Export Configuration to JSON
Actors: System Administrator, Team Lead
Key Behaviors:
- Export configuration to JSON file
- Choose export location
- Receive success notification
Edge Cases:
- Special characters in values
- Directory doesn't exist
- Configuration is large
Error Scenarios:
- Disk is full
- Permission denied
- File already exists
```

### Generated Scenarios

```gherkin
Scenario: Administrator successfully exports configuration to file
  Given configuration with all system settings is loaded
  When administrator clicks "Export Configuration" button
  Then JSON file is created in default location
    And file contains complete configuration

Scenario: Administrator selects custom export location
  Given configuration is loaded
    And ~/backups directory exists
  When administrator selects ~/backups/config.json as export location
  Then JSON file is created at ~/backups/config.json
    And previous location is not used

Scenario: Export displays success notification
  Given configuration is loaded
  When administrator clicks Export button
  Then success notification appears: "Configuration exported successfully"
    And notification disappears after 5 seconds

Scenario: Export handles special characters correctly
  Given configuration contains special characters:
    - Double quotes in database password
    - Unicode characters in admin name (José)
    - Newlines in description field
  When administrator exports to JSON
  Then all special characters are properly escaped
    And exported JSON is valid (parseable by standard tools)

Scenario: Export creates missing directory automatically
  Given configuration is loaded
    And ~/backups directory does not exist
  When administrator exports to ~/backups/config.json
  Then ~/backups directory is created
    And JSON file is created in new directory
    And no error message appears

Scenario: Export succeeds with very large configuration
  Given configuration contains 5000+ settings
  When administrator exports to JSON
  Then export completes within 30 seconds
    And all 5000+ settings appear in JSON file
    And file size is reasonable (not bloated)

Scenario: Export fails when disk has insufficient space
  Given configuration is ready to export (size would be 500MB)
    And disk has only 100MB free space
  When administrator attempts export
  Then error message appears: "Insufficient disk space: need 500MB, have 100MB"
    And no partial file is created

Scenario: Export fails when directory is read-only
  Given configuration is loaded
    And selected directory permissions are read-only (no write)
  When administrator attempts export
  Then error message appears: "Permission denied: cannot write to [path]"
    And no file is created

Scenario: Export prompts user when file already exists
  Given configuration is loaded
    And file already exists at ~/backups/config.json
  When administrator exports to ~/backups/config.json
  Then dialog appears: "File ~/backups/config.json already exists. Overwrite?"
    And administrator can choose to overwrite or cancel
```

### Validation Checklist Results

✅ **Syntax:** All scenarios follow Given/When/Then structure
✅ **Consistency:** "configuration", "export", "administrator" used consistently
✅ **Coverage:** 3 behaviors + 3 edge cases + 3 errors = 9 scenarios
✅ **Clarity:** All Given/When/Then are specific and measurable
✅ **Atomicity:** Each scenario tests one behavior

---

## Example 2: User Authentication Feature

### Feature Narrative

```
Feature Title: Enable Two-Factor Authentication
Actors: End User, Account Owner
Key Behaviors:
- User enables 2FA
- User selects authentication method (SMS or app)
- User receives verification code
- 2FA is required on next login
Edge Cases:
- User changes phone number after enabling 2FA
- User uses backup codes
- SMS delivery is delayed
Error Scenarios:
- SMS code entered incorrectly (multiple attempts)
- Code expires before user enters it
- Phone unreachable
- User loses access to authenticator app
```

### Generated Scenarios

```gherkin
Scenario: User successfully enables 2FA with SMS method
  Given user is logged in
    And user is on Security Settings page
  When user clicks "Enable Two-Factor Authentication"
    And selects "SMS verification" as method
    And enters phone number +1-555-0123
  Then SMS code is sent to +1-555-0123
    And user sees: "Enter 6-digit code sent to +1-555-0123"
    And countdown timer shows 5 minutes remaining

Scenario: User receives and enters SMS verification code
  Given user has selected SMS method and entered phone
    And SMS code 123456 has been sent
  When user enters SMS code 123456
  Then system confirms: "2FA enabled successfully"
    And Security Settings page shows "Two-Factor Authentication: ENABLED"

Scenario: User enables 2FA with authenticator app
  Given user is on Security Settings page
  When user clicks "Enable Two-Factor Authentication"
    And selects "Authenticator App" as method
  Then QR code is displayed
    And user can scan QR code with authenticator app
    And after scanning, user is prompted to enter 6-digit code from app

Scenario: Backup codes are provided when 2FA is enabled
  Given user has just enabled 2FA
  When 2FA setup completes
  Then user sees backup codes: [CODE1], [CODE2], [CODE3], [CODE4], [CODE5]
    And user is warned: "Save these codes in a safe place"
    And user can download backup codes as file

Scenario: User logs in and is prompted for second factor
  Given user has 2FA enabled with SMS
    And user is on login page
  When user enters email and password correctly
  Then login does NOT complete
    And user sees: "Verification code required"
    And SMS code is automatically sent
    And user must enter code to complete login

Scenario: Incorrect SMS code rejects user
  Given user needs to enter SMS code to complete login
    And correct code is 123456
  When user enters incorrect code 000000
  Then error appears: "Invalid verification code"
    And login is still pending (user can retry)

Scenario: User blocked after too many incorrect codes
  Given user needs to enter SMS code
  When user enters wrong code 5 times
  Then login is blocked: "Too many failed attempts. Try again in 15 minutes."
    And SMS code is invalidated

Scenario: User can use backup code when SMS unavailable
  Given user has 2FA enabled with SMS
    And phone is not receiving SMS
    And user has backup codes [BACKUP1], [BACKUP2], [BACKUP3]
  When user enters backup code BACKUP1 instead of SMS code
  Then login completes successfully
    And BACKUP1 is marked as used
    And user can only use remaining backup codes

Scenario: SMS code expires if not entered in time
  Given user needs to enter SMS code
    And code expires after 10 minutes
  When user waits 11 minutes without entering code
  Then code is no longer valid
    And error appears: "Code expired. Request a new code."
    And user can click "Resend Code" to get new SMS

Scenario: User can change phone number and re-verify
  Given user has 2FA enabled with phone +1-555-0123
    And user changed their phone to +1-555-9999
  When user goes to Security Settings
    And clicks "Update Phone Number"
    And enters new phone +1-555-9999
  Then new SMS code is sent to +1-555-9999
    And user must enter code to confirm change
    And 2FA now uses new phone number

Scenario: User loses access to authenticator app
  Given user has 2FA enabled with authenticator app
    And authenticator app was deleted
    And user does not have backup codes
  When user tries to log in
    And cannot generate code from missing app
  Then user sees: "Can't verify? Contact Support"
    And user can click link to support ticket
```

### Validation Checklist Results

✅ **Syntax:** All scenarios follow Given/When/Then structure
✅ **Consistency:** "user", "2FA", "code", "SMS" used consistently
✅ **Coverage:** 4 behaviors + 4 edge cases + 4 error scenarios
✅ **Clarity:** All Given/When/Then are specific and measurable
✅ **Atomicity:** Each scenario tests one behavior

---

## Example 3: Shopping Cart Feature

### Feature Narrative

```
Feature Title: Add Items to Shopping Cart
Actors: Shopper, Registered User, Guest
Key Behaviors:
- Add product to cart
- Update quantity
- Remove item
- View cart total
Edge Cases:
- Add same item twice (quantity increases)
- Item becomes out of stock after adding
- Item price changes while in cart
Error Scenarios:
- Item no longer available
- Out of stock
- Quantity exceeds available stock
```

### Generated Scenarios

```gherkin
Scenario: Shopper adds item to cart
  Given shopper is viewing product "Widget A" ($29.99)
  When shopper clicks "Add to Cart"
  Then item is added to cart
    And cart shows "1 item" in header
    And success notification appears: "Widget A added to cart"

Scenario: Shopper updates item quantity
  Given "Widget A" is in cart with quantity 1
  When shopper changes quantity to 3
  Then cart updates to show quantity 3
    And total price updates to $89.97 (3 × $29.99)

Scenario: Shopper removes item from cart
  Given cart contains "Widget A" and "Gadget B"
  When shopper clicks "Remove" next to Widget A
  Then Widget A is removed
    And cart now contains only "Gadget B"
    And total price updates accordingly

Scenario: Cart total displays correctly with multiple items
  Given cart contains:
    - Widget A: $29.99 × 2 = $59.98
    - Gadget B: $19.99 × 1 = $19.99
  When shopper views cart
  Then cart total shows: $79.97
    And tax (if applicable) is calculated correctly

Scenario: Adding same item twice increases quantity
  Given "Widget A" is in cart with quantity 1
  When shopper finds Widget A again and clicks "Add to Cart"
  Then quantity increases to 2
    And only one "Widget A" line appears in cart
    And price updates to 2 × $29.99 = $59.98

Scenario: Item becomes out of stock after adding to cart
  Given "Widget A" is in cart with quantity 2
    And Widget A is suddenly out of stock (sold out)
  When shopper views cart
  Then warning appears: "Widget A is no longer in stock"
    And shopper can keep in cart or remove
    And checkout is blocked until removed or restocked

Scenario: Item price changes while in cart
  Given Widget A is in cart at $29.99
    And price is updated to $34.99 by admin
  When shopper views cart
  Then cart shows updated price $34.99
    And old price $29.99 is crossed out
    And total is recalculated
    And notification: "Price updated: Widget A now $34.99"

Scenario: Item is no longer available in system
  Given Widget A is in cart
    And Widget A is deleted from product catalog
  When shopper views cart
  Then item shows as "No longer available"
    And cannot proceed to checkout
    And shopper must remove to continue

Scenario: Adding quantity exceeding available stock fails
  Given Widget A has only 5 available
    And Widget A is in cart with quantity 3
  When shopper tries to change quantity to 8
  Then quantity change is rejected
    And error appears: "Only 5 available. You have 3. Can add 2 more."
    And quantity remains at 3

Scenario: Cart persists after logout and login
  Given shopper has items in cart
    And shopper is logged in
  When shopper logs out
    And logs back in
  Then same items appear in cart
    And quantities are preserved
    And prices reflect current values
```

### Validation Checklist Results

✅ **Syntax:** All scenarios follow Given/When/Then structure
✅ **Consistency:** "item", "cart", "quantity", "shopper", "price" used consistently
✅ **Coverage:** 4 behaviors + 3 edge cases + 3 error scenarios
✅ **Clarity:** All Given/When/Then are specific and measurable
✅ **Atomicity:** Each scenario tests one behavior

---

## Common Patterns in Good Scenarios

### Pattern 1: Clear State Description

```gherkin
Given [adjective] [noun] in [location]
```

✅ **Good:** `Given Widget A is in cart with quantity 2`
❌ **Bad:** `Given there's a widget`

### Pattern 2: Specific Actions

```gherkin
When [actor] [verb] [object]
```

✅ **Good:** `When shopper clicks "Add to Cart" button`
❌ **Bad:** `When shopper does something`

### Pattern 3: Measurable Outcomes

```gherkin
Then [observable result] [showing/containing/displaying] [specific value]
```

✅ **Good:** `Then cart shows "1 item" in header`
❌ **Bad:** `Then the cart updates`

### Pattern 4: Related Verifications

```gherkin
Then [outcome 1]
  And [related outcome 2]
  And [related outcome 3]
```

✅ **Good:**
```gherkin
Then item is added to cart
  And cart header shows "1 item"
  And success notification appears
```

❌ **Bad:**
```gherkin
Then item is added
  And user is happy
  And notification shows
  And analytics logs event
  And email sent
  And history updated
```
(Too many unrelated assertions - split into separate scenarios)

---

## Study Guide

**Before writing your own scenarios:**

1. **Read Example 1** — Understand the pattern of happy path + edge cases + errors
2. **Study the quality checklist** — Know what makes a scenario valid
3. **Check terminology** — Notice how good examples use consistent domain language
4. **Review clarity** — See how specific measurements and values are used
5. **Apply to your feature** — Use these patterns for your own scenarios

**Red flags to avoid:**

- ❌ Scenario with no When (missing action)
- ❌ Multiple actions in When (split into scenarios)
- ❌ Vague outcomes in Then (use specific values)
- ❌ Inconsistent terminology (use glossary)
- ❌ Only happy path (add edge cases + errors)
