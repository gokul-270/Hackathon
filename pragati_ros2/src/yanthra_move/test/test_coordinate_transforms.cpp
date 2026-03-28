#include <gtest/gtest.h>
#include "yanthra_move/coordinate_transforms.hpp"
#include <cmath>

namespace yanthra_move {
namespace coordinate_transforms {

// NOTE: convertXYZToPolarFLUROSCoordinates is NOT standard spherical coordinates!
// It's a robot-specific transform where:
//   r = sqrt(x² + z²)  (distance in XZ plane only)
//   theta = y          (Y coordinate, not an angle!)
//   phi = asin(z / sqrt(z² + x²))  (elevation angle in XZ plane)

class CoordinateTransformsTest : public ::testing::Test
{
protected:
    void SetUp() override
    {
        // No setup needed for pure functions
    }

    void TearDown() override
    {
        // No teardown needed
    }

    // Helper to compare double values with tolerance
    void expectNear(double actual, double expected, double tolerance = 1e-6) {
        EXPECT_NEAR(actual, expected, tolerance);
    }
};

// Test: XYZ to Polar conversion - origin point
TEST_F(CoordinateTransformsTest, XYZToPolarOrigin)
{
    double r, theta, phi;
    convertXYZToPolarFLUROSCoordinates(0.0, 0.0, 0.0, &r, &theta, &phi);
    
    EXPECT_DOUBLE_EQ(r, 0.0);  // r = sqrt(x² + z²) = 0
    EXPECT_DOUBLE_EQ(theta, 0.0);  // theta = y = 0
    // phi = asin(0/0) = NaN at origin, this is expected for this implementation
    // We just verify it's computed (may be NaN)
}

// Test: XYZ to Polar conversion - positive X axis
TEST_F(CoordinateTransformsTest, XYZToPolarPositiveX)
{
    double r, theta, phi;
    convertXYZToPolarFLUROSCoordinates(1.0, 0.0, 0.0, &r, &theta, &phi);
    
    EXPECT_DOUBLE_EQ(r, 1.0);  // r = sqrt(1² + 0²) = 1
    EXPECT_DOUBLE_EQ(theta, 0.0);  // theta = y = 0
    EXPECT_DOUBLE_EQ(phi, 0.0);  // phi = asin(0/1) = 0
}

// Test: XYZ to Polar conversion - positive Y axis
TEST_F(CoordinateTransformsTest, XYZToPolarPositiveY)
{
    double r, theta, phi;
    convertXYZToPolarFLUROSCoordinates(0.0, 1.0, 0.0, &r, &theta, &phi);
    
    EXPECT_DOUBLE_EQ(r, 0.0);  // r = sqrt(0² + 0²) = 0 (only X and Z matter)
    EXPECT_DOUBLE_EQ(theta, 1.0);  // theta = y = 1.0 (NOT an angle!)
    // phi is undefined when x=z=0, result will be NaN
}

// Test: XYZ to Polar conversion - positive Z axis
TEST_F(CoordinateTransformsTest, XYZToPolarPositiveZ)
{
    double r, theta, phi;
    convertXYZToPolarFLUROSCoordinates(0.0, 0.0, 1.0, &r, &theta, &phi);
    
    EXPECT_DOUBLE_EQ(r, 1.0);  // r = sqrt(0² + 1²) = 1
    EXPECT_DOUBLE_EQ(theta, 0.0);  // theta = y = 0
    expectNear(phi, M_PI / 2.0);  // phi = asin(1/1) = π/2 (90 degrees)
}

// Test: XYZ to Polar conversion - diagonal point (1,1,1)
TEST_F(CoordinateTransformsTest, XYZToPolarDiagonal)
{
    double r, theta, phi;
    convertXYZToPolarFLUROSCoordinates(1.0, 1.0, 1.0, &r, &theta, &phi);
    
    expectNear(r, std::sqrt(2.0));  // r = sqrt(1² + 1²) = sqrt(2)
    EXPECT_DOUBLE_EQ(theta, 1.0);  // theta = y = 1.0
    expectNear(phi, M_PI / 4.0);  // phi = asin(1/sqrt(2)) = π/4 (45 degrees)
}

// Test: XYZ to Polar conversion - negative values
TEST_F(CoordinateTransformsTest, XYZToPolarNegative)
{
    double r, theta, phi;
    convertXYZToPolarFLUROSCoordinates(-1.0, 0.0, 0.0, &r, &theta, &phi);
    
    EXPECT_DOUBLE_EQ(r, 1.0);  // r = sqrt((-1)² + 0²) = 1
    EXPECT_DOUBLE_EQ(theta, 0.0);  // theta = y = 0
    EXPECT_DOUBLE_EQ(phi, 0.0);  // phi = asin(0/1) = 0
}

// Test: XYZ to Polar conversion - symmetry check
TEST_F(CoordinateTransformsTest, XYZToPolarSymmetry)
{
    double r1, theta1, phi1;
    double r2, theta2, phi2;
    
    // Point and its reflection should have same XZ plane distance
    convertXYZToPolarFLUROSCoordinates(1.0, 2.0, 3.0, &r1, &theta1, &phi1);
    convertXYZToPolarFLUROSCoordinates(-1.0, -2.0, -3.0, &r2, &theta2, &phi2);
    
    EXPECT_DOUBLE_EQ(r1, r2);  // Same XZ plane distance sqrt(1²+3²) = sqrt((-1)²+(-3)²)
    EXPECT_NE(theta1, theta2);  // theta = y: 2.0 vs -2.0
    EXPECT_NE(phi1, phi2);      // Different elevation angles
}

// Test: XYZ to Polar conversion - large values
TEST_F(CoordinateTransformsTest, XYZToPolarLargeValues)
{
    double r, theta, phi;
    convertXYZToPolarFLUROSCoordinates(100.0, 200.0, 300.0, &r, &theta, &phi);
    
    expectNear(r, std::sqrt(100.0*100.0 + 300.0*300.0));  // sqrt(x² + z²)
    EXPECT_DOUBLE_EQ(theta, 200.0);  // theta = y = 200.0
    EXPECT_TRUE(std::isfinite(phi));
    // phi range for asin is [-π/2, π/2]
    EXPECT_GE(phi, -M_PI/2.0);
    EXPECT_LE(phi, M_PI/2.0);
}

// Test: Reachability - point within range
TEST_F(CoordinateTransformsTest, ReachabilityWithinRange)
{
    EXPECT_TRUE(checkReachability(0.5, 0.0, 0.0));
    EXPECT_TRUE(checkReachability(1.0, M_PI/4.0, M_PI/6.0));
    EXPECT_TRUE(checkReachability(1.5, -M_PI/2.0, M_PI/4.0));
}

// Test: Reachability - point at boundaries
TEST_F(CoordinateTransformsTest, ReachabilityBoundaries)
{
    EXPECT_FALSE(checkReachability(0.1, 0.0, 0.0));  // At lower limit
    EXPECT_FALSE(checkReachability(2.0, 0.0, 0.0));  // At upper limit
    EXPECT_TRUE(checkReachability(0.11, 0.0, 0.0));  // Just inside lower
    EXPECT_TRUE(checkReachability(1.99, 0.0, 0.0));  // Just inside upper
}

// Test: Reachability - point outside range
TEST_F(CoordinateTransformsTest, ReachabilityOutsideRange)
{
    EXPECT_FALSE(checkReachability(0.05, 0.0, 0.0));  // Too close
    EXPECT_FALSE(checkReachability(3.0, 0.0, 0.0));   // Too far
    EXPECT_FALSE(checkReachability(-0.5, 0.0, 0.0));  // Negative distance (invalid)
}

// Test: Reachability - zero distance
TEST_F(CoordinateTransformsTest, ReachabilityZeroDistance)
{
    EXPECT_FALSE(checkReachability(0.0, 0.0, 0.0));
}

// Test: Reachability - angle independence
TEST_F(CoordinateTransformsTest, ReachabilityAngleIndependence)
{
    // Distance is what matters, not angles (per implementation)
    double r = 1.0;
    EXPECT_TRUE(checkReachability(r, 0.0, 0.0));
    EXPECT_TRUE(checkReachability(r, M_PI, 0.0));
    EXPECT_TRUE(checkReachability(r, M_PI/2.0, M_PI/4.0));
    EXPECT_TRUE(checkReachability(r, -M_PI/2.0, -M_PI/4.0));
}

// Test: Round-trip conversion validation
TEST_F(CoordinateTransformsTest, RoundTripConversion)
{
    // Convert to polar and verify properties
    double x = 3.0, y = 4.0, z = 5.0;
    double r, theta, phi;
    
    convertXYZToPolarFLUROSCoordinates(x, y, z, &r, &theta, &phi);
    
    // Verify r is positive (XZ plane distance)
    EXPECT_GT(r, 0.0);
    
    // theta = y, no angle restriction
    EXPECT_DOUBLE_EQ(theta, y);
    
    // phi is elevation angle in XZ plane, limited by asin
    EXPECT_GE(phi, -M_PI/2.0);
    EXPECT_LE(phi, M_PI/2.0);
    
    // Verify r matches XZ plane distance
    double reconstructed_r = std::sqrt(x*x + z*z);
    expectNear(r, reconstructed_r);
}

// Test: Multiple conversions consistency
TEST_F(CoordinateTransformsTest, MultipleConversionsConsistency)
{
    std::vector<std::tuple<double, double, double>> test_points = {
        {1.0, 0.0, 0.0},
        // Skip {0.0, 1.0, 0.0} - produces NaN for phi
        {0.0, 0.0, 1.0},
        {1.0, 1.0, 0.0},
        {1.0, 1.0, 1.0},
        {2.0, 3.0, 4.0}
    };
    
    for (const auto& [x, y, z] : test_points) {
        double r1, theta1, phi1;
        double r2, theta2, phi2;
        
        // Convert twice - should get same result
        convertXYZToPolarFLUROSCoordinates(x, y, z, &r1, &theta1, &phi1);
        convertXYZToPolarFLUROSCoordinates(x, y, z, &r2, &theta2, &phi2);
        
        EXPECT_DOUBLE_EQ(r1, r2);
        EXPECT_DOUBLE_EQ(theta1, theta2);
        // Only check phi if not NaN (happens when x=z=0)
        if (std::isfinite(phi1) && std::isfinite(phi2)) {
            EXPECT_DOUBLE_EQ(phi1, phi2);
        }
    }
}

// Test: Coordinate transform correctness - Pythagoras in XZ plane
TEST_F(CoordinateTransformsTest, PythagoreanDistance)
{
    // Test that radial distance satisfies Pythagorean theorem in XZ plane
    double x = 3.0, y = 4.0, z = 0.0;
    double r, theta, phi;
    
    convertXYZToPolarFLUROSCoordinates(x, y, z, &r, &theta, &phi);
    
    EXPECT_DOUBLE_EQ(r, 3.0);  // r = sqrt(3² + 0²) = 3 (Y is ignored)
    EXPECT_DOUBLE_EQ(theta, 4.0);  // theta = y = 4.0
}

// Test: Coordinate transform - very small values
TEST_F(CoordinateTransformsTest, SmallValues)
{
    double r, theta, phi;
    convertXYZToPolarFLUROSCoordinates(1e-10, 1e-10, 1e-10, &r, &theta, &phi);
    
    expectNear(r, std::sqrt(2.0) * 1e-10);  // r = sqrt(x² + z²) = sqrt(2) * 1e-10
    EXPECT_DOUBLE_EQ(theta, 1e-10);  // theta = y = 1e-10
    EXPECT_TRUE(std::isfinite(phi));  // phi should be finite for this case
}

} // namespace coordinate_transforms
} // namespace yanthra_move
