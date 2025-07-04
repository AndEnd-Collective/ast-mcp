// Test JavaScript file with various issues that our rules should catch

// This should trigger js-no-var
var oldStyle = "should use let or const";

// This should trigger js-use-strict-equality
if (value == "test") {
    console.log("Should use ===");
}

// This should trigger js-no-console-log
console.log("Debug message");

// This should trigger js-no-function-in-block
if (condition) {
    function badFunction() {
        return "Should not declare functions in blocks";
    }
}

// This should trigger js-no-unused-vars
var unusedVariable = "never used";

// This should trigger js-missing-semicolon
let missingSemicolon = "end without semicolon"

// Some good code
function goodFunction() {
    const message = "This follows best practices";
    return message;
}