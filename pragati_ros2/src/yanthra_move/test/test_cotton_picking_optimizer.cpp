// Copyright 2025 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include <gtest/gtest.h>
#include "yanthra_move/cotton_picking_optimizer.hpp"

#include <cmath>
#include <vector>
#include <geometry_msgs/msg/point.hpp>
#include <geometry_msgs/msg/point_stamped.hpp>

namespace yanthra_move {

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

geometry_msgs::msg::Point makePoint(double x, double y, double z) {
    geometry_msgs::msg::Point p;
    p.x = x; p.y = y; p.z = z;
    return p;
}

geometry_msgs::msg::PointStamped makePointStamped(double x, double y, double z,
                                                   const std::string& frame = "base_link") {
    geometry_msgs::msg::PointStamped ps;
    ps.header.frame_id = frame;
    ps.point = makePoint(x, y, z);
    return ps;
}

/// Compute phi (base rotation angle) the same way the implementation does.
double phi(const geometry_msgs::msg::Point& p) {
    return std::atan2(p.y, p.x);
}

/// Compute theta (elevation angle) the same way the implementation does.
double theta(const geometry_msgs::msg::Point& p) {
    double r_xy = std::sqrt(p.x * p.x + p.y * p.y);
    return std::atan2(p.z, r_xy);
}

// ---------------------------------------------------------------------------
// Test Fixture
// ---------------------------------------------------------------------------

class CottonPickingOptimizerTest : public ::testing::Test {
protected:
    using Strategy = CottonPickingOptimizer::Strategy;

    /// Build a set of points spread across different phi angles and elevations,
    /// useful for most strategy tests.
    std::vector<geometry_msgs::msg::Point> makeSpreadPoints() {
        // Deliberately out-of-order phi values so sorting is observable.
        //   Point A: phi ~  0.78  (quadrant I)
        //   Point B: phi ~ -0.78  (quadrant IV)
        //   Point C: phi ~  2.36  (quadrant II)
        //   Point D: phi ~ -2.36  (quadrant III)
        //   Point E: phi ~  0.0   (positive X axis)
        return {
            makePoint(1.0,  1.0,  0.5),  // A
            makePoint(1.0, -1.0,  0.3),  // B
            makePoint(-1.0, 1.0,  0.8),  // C
            makePoint(-1.0, -1.0, 0.1),  // D
            makePoint(2.0,  0.0,  0.4),  // E
        };
    }

    /// Build a grid of points for raster-scan tests.
    /// Three rows (Y = 0.0, 0.10, 0.20) each with three columns (X = 1, 2, 3).
    std::vector<geometry_msgs::msg::Point> makeGridPoints() {
        return {
            makePoint(3.0, 0.10, 0.0),
            makePoint(1.0, 0.20, 0.0),
            makePoint(2.0, 0.00, 0.0),
            makePoint(1.0, 0.10, 0.0),
            makePoint(3.0, 0.20, 0.0),
            makePoint(1.0, 0.00, 0.0),
            makePoint(2.0, 0.10, 0.0),
            makePoint(2.0, 0.20, 0.0),
            makePoint(3.0, 0.00, 0.0),
        };
    }
};

// ===================================================================
// 3.1  NONE strategy — output order matches input order
// ===================================================================

TEST_F(CottonPickingOptimizerTest, NoneStrategyPreservesOrder) {
    auto pts = makeSpreadPoints();
    auto original = pts;  // copy

    CottonPickingOptimizer::optimizePickingOrder(pts, Strategy::NONE);

    ASSERT_EQ(pts.size(), original.size());
    for (size_t i = 0; i < pts.size(); ++i) {
        EXPECT_DOUBLE_EQ(pts[i].x, original[i].x);
        EXPECT_DOUBLE_EQ(pts[i].y, original[i].y);
        EXPECT_DOUBLE_EQ(pts[i].z, original[i].z);
    }
}

// ===================================================================
// 3.2  PHI_SWEEP strategy — sorted by phi ascending
// ===================================================================

TEST_F(CottonPickingOptimizerTest, PhiSweepSortsByPhiAscending) {
    auto pts = makeSpreadPoints();

    CottonPickingOptimizer::optimizePickingOrder(pts, Strategy::PHI_SWEEP);

    for (size_t i = 1; i < pts.size(); ++i) {
        double phi_prev = phi(pts[i - 1]);
        double phi_curr = phi(pts[i]);
        EXPECT_LE(phi_prev, phi_curr + 1e-9)
            << "Position " << i << " has phi " << phi_curr
            << " which is less than predecessor " << phi_prev;
    }
}

TEST_F(CottonPickingOptimizerTest, PhiSweepKnownOrder) {
    // Points with exact known phi values for deterministic check.
    // phi = atan2(y, x)
    std::vector<geometry_msgs::msg::Point> pts = {
        makePoint(1.0,  0.0, 0.0),  // phi = 0
        makePoint(0.0,  1.0, 0.0),  // phi = pi/2
        makePoint(0.0, -1.0, 0.0),  // phi = -pi/2
        makePoint(-1.0, 0.0, 0.0),  // phi = pi
    };

    CottonPickingOptimizer::optimizePickingOrder(pts, Strategy::PHI_SWEEP);

    // Expected order: -pi/2, 0, pi/2, pi
    EXPECT_NEAR(phi(pts[0]), -M_PI / 2.0, 1e-9);
    EXPECT_NEAR(phi(pts[1]),  0.0,         1e-9);
    EXPECT_NEAR(phi(pts[2]),  M_PI / 2.0,  1e-9);
    EXPECT_NEAR(phi(pts[3]),  M_PI,         1e-9);
}

// ===================================================================
// 3.3  HIERARCHICAL strategy — phi zones then theta within zone
// ===================================================================

TEST_F(CottonPickingOptimizerTest, HierarchicalSortsByPhiThenTheta) {
    auto pts = makeSpreadPoints();

    CottonPickingOptimizer::optimizePickingOrder(
        pts, Strategy::HIERARCHICAL, 0.0, 0.05);

    // Global invariant: phi is non-decreasing (allowing threshold grouping).
    for (size_t i = 1; i < pts.size(); ++i) {
        double dphi = phi(pts[i]) - phi(pts[i - 1]);
        // Either phi increased, or it's within threshold (same zone).
        EXPECT_GE(dphi, -0.05 - 1e-9)
            << "Position " << i << ": phi decreased beyond threshold";
    }
}

TEST_F(CottonPickingOptimizerTest, HierarchicalThetaWithinSamePhiZone) {
    // Two points with nearly the same phi but different theta.
    // phi_threshold default = 0.05 rad.
    double base_x = 2.0;
    double base_y = 1.0;
    // Both share the same (x,y) so their phi is identical.
    // Different z gives different theta.
    std::vector<geometry_msgs::msg::Point> pts = {
        makePoint(base_x, base_y, 1.5),  // higher theta
        makePoint(base_x, base_y, 0.1),  // lower theta
    };

    CottonPickingOptimizer::optimizePickingOrder(
        pts, Strategy::HIERARCHICAL, 0.0, 0.05);

    // Within the same phi zone, theta should be ascending.
    EXPECT_LE(theta(pts[0]), theta(pts[1]) + 1e-9);
}

TEST_F(CottonPickingOptimizerTest, HierarchicalPhiDominatesOverTheta) {
    // Two points in different phi zones — phi ordering dominates even if
    // the first has a higher theta.
    std::vector<geometry_msgs::msg::Point> pts = {
        makePoint(0.0, 1.0, 10.0),  // phi = pi/2, high theta
        makePoint(1.0, 0.0, 0.0),   // phi = 0, low theta
    };

    CottonPickingOptimizer::optimizePickingOrder(
        pts, Strategy::HIERARCHICAL, 0.0, 0.05);

    // phi=0 should come before phi=pi/2.
    EXPECT_NEAR(phi(pts[0]), 0.0,        1e-9);
    EXPECT_NEAR(phi(pts[1]), M_PI / 2.0, 1e-9);
}

// ===================================================================
// 3.4  RASTER_SCAN strategy — serpentine sweep
// ===================================================================

TEST_F(CottonPickingOptimizerTest, RasterScanSerpentinePattern) {
    auto pts = makeGridPoints();

    CottonPickingOptimizer::optimizePickingOrder(pts, Strategy::RASTER_SCAN);

    ASSERT_EQ(pts.size(), 9u);

    // Row 0 (Y = 0.00): left-to-right => X = 1, 2, 3
    EXPECT_NEAR(pts[0].x, 1.0, 1e-9);
    EXPECT_NEAR(pts[1].x, 2.0, 1e-9);
    EXPECT_NEAR(pts[2].x, 3.0, 1e-9);

    // Row 1 (Y = 0.10): right-to-left => X = 3, 2, 1
    EXPECT_NEAR(pts[3].x, 3.0, 1e-9);
    EXPECT_NEAR(pts[4].x, 2.0, 1e-9);
    EXPECT_NEAR(pts[5].x, 1.0, 1e-9);

    // Row 2 (Y = 0.20): left-to-right => X = 1, 2, 3
    EXPECT_NEAR(pts[6].x, 1.0, 1e-9);
    EXPECT_NEAR(pts[7].x, 2.0, 1e-9);
    EXPECT_NEAR(pts[8].x, 3.0, 1e-9);
}

TEST_F(CottonPickingOptimizerTest, RasterScanRowsOrderedByY) {
    auto pts = makeGridPoints();

    CottonPickingOptimizer::optimizePickingOrder(pts, Strategy::RASTER_SCAN);

    // Verify Y is non-decreasing across the sequence (row boundaries).
    double prev_y = -std::numeric_limits<double>::infinity();
    for (const auto& p : pts) {
        double row_y = std::round(p.y * 100.0) / 100.0;
        EXPECT_GE(row_y, prev_y - 1e-9);
        prev_y = row_y;
    }
}

// ===================================================================
// 3.5  NEAREST_FIRST strategy — energy-weighted nearest neighbor
// ===================================================================

TEST_F(CottonPickingOptimizerTest, NearestFirstStartsFromClosestPhi) {
    // current_phi = 0.  Closest phi to 0 is point on positive X axis.
    std::vector<geometry_msgs::msg::Point> pts = {
        makePoint(0.0,  1.0, 0.0),  // phi = pi/2
        makePoint(1.0,  0.0, 0.0),  // phi = 0   <-- closest to current_phi=0
        makePoint(0.0, -1.0, 0.0),  // phi = -pi/2
    };

    CottonPickingOptimizer::optimizePickingOrder(pts, Strategy::NEAREST_FIRST, 0.0);

    // First picked should be the one with phi closest to 0.
    EXPECT_NEAR(phi(pts[0]), 0.0, 1e-9);
}

TEST_F(CottonPickingOptimizerTest, NearestFirstRespectsCurrentPhi) {
    // current_phi = pi/2.  The point at phi=pi/2 should be picked first.
    std::vector<geometry_msgs::msg::Point> pts = {
        makePoint(1.0,  0.0, 0.0),  // phi = 0
        makePoint(0.0,  1.0, 0.0),  // phi = pi/2
        makePoint(-1.0, 0.0, 0.0),  // phi = pi
    };

    CottonPickingOptimizer::optimizePickingOrder(pts, Strategy::NEAREST_FIRST, M_PI / 2.0);

    EXPECT_NEAR(phi(pts[0]), M_PI / 2.0, 1e-9);
}

TEST_F(CottonPickingOptimizerTest, NearestFirstVisitsAllPoints) {
    auto pts = makeSpreadPoints();
    size_t n = pts.size();

    CottonPickingOptimizer::optimizePickingOrder(pts, Strategy::NEAREST_FIRST, 0.0);

    EXPECT_EQ(pts.size(), n);
}

TEST_F(CottonPickingOptimizerTest, NearestFirstGreedyProgression) {
    // A chain where nearest-neighbor should follow a clear sequence.
    // Points along the positive X axis with increasing Y — each next
    // point is the energy-nearest.
    std::vector<geometry_msgs::msg::Point> pts = {
        makePoint(1.0, 0.3, 0.0),  // phi ~ 0.29
        makePoint(1.0, 0.0, 0.0),  // phi = 0.0
        makePoint(1.0, 0.6, 0.0),  // phi ~ 0.54
        makePoint(1.0, 0.9, 0.0),  // phi ~ 0.73
    };

    CottonPickingOptimizer::optimizePickingOrder(pts, Strategy::NEAREST_FIRST, 0.0);

    // Should start with phi closest to 0 and greedily progress.
    // With phi dominating the energy cost (weight 10), the sequence
    // should follow ascending phi.
    for (size_t i = 1; i < pts.size(); ++i) {
        EXPECT_GE(phi(pts[i]), phi(pts[i - 1]) - 1e-9)
            << "Greedy path went backwards at index " << i;
    }
}

// ===================================================================
// 3.6  estimateEnergySavings
// ===================================================================

TEST_F(CottonPickingOptimizerTest, EnergySavingsNoneReturnsZero) {
    auto pts = makeSpreadPoints();
    double savings = CottonPickingOptimizer::estimateEnergySavings(pts, Strategy::NONE);
    EXPECT_DOUBLE_EQ(savings, 0.0);
}

TEST_F(CottonPickingOptimizerTest, EnergySavingsSinglePointReturnsZero) {
    std::vector<geometry_msgs::msg::Point> pts = { makePoint(1.0, 2.0, 3.0) };
    // All strategies should return 0 for a single point.
    EXPECT_DOUBLE_EQ(CottonPickingOptimizer::estimateEnergySavings(pts, Strategy::NONE), 0.0);
    EXPECT_DOUBLE_EQ(CottonPickingOptimizer::estimateEnergySavings(pts, Strategy::PHI_SWEEP), 0.0);
    EXPECT_DOUBLE_EQ(CottonPickingOptimizer::estimateEnergySavings(pts, Strategy::HIERARCHICAL), 0.0);
    EXPECT_DOUBLE_EQ(CottonPickingOptimizer::estimateEnergySavings(pts, Strategy::NEAREST_FIRST), 0.0);
    EXPECT_DOUBLE_EQ(CottonPickingOptimizer::estimateEnergySavings(pts, Strategy::RASTER_SCAN), 0.0);
}

TEST_F(CottonPickingOptimizerTest, EnergySavingsPhiSweep50Percent) {
    auto pts = makeSpreadPoints();
    double savings = CottonPickingOptimizer::estimateEnergySavings(pts, Strategy::PHI_SWEEP);
    // optimized = current * 0.5  =>  savings = (1-0.5)/1 * 100 = 50
    EXPECT_NEAR(savings, 50.0, 1e-9);
}

TEST_F(CottonPickingOptimizerTest, EnergySavingsHierarchical65Percent) {
    auto pts = makeSpreadPoints();
    double savings = CottonPickingOptimizer::estimateEnergySavings(pts, Strategy::HIERARCHICAL);
    // optimized = current * 0.35  =>  savings = (1-0.35)/1 * 100 = 65
    EXPECT_NEAR(savings, 65.0, 1e-9);
}

TEST_F(CottonPickingOptimizerTest, EnergySavingsNearestFirst40Percent) {
    auto pts = makeSpreadPoints();
    double savings = CottonPickingOptimizer::estimateEnergySavings(pts, Strategy::NEAREST_FIRST);
    // optimized = current * 0.6  =>  savings = (1-0.6)/1 * 100 = 40
    EXPECT_NEAR(savings, 40.0, 1e-9);
}

TEST_F(CottonPickingOptimizerTest, EnergySavingsRasterScanZeroPercent) {
    auto pts = makeSpreadPoints();
    double savings = CottonPickingOptimizer::estimateEnergySavings(pts, Strategy::RASTER_SCAN);
    // optimized = current * 1.0  =>  savings = 0
    EXPECT_NEAR(savings, 0.0, 1e-9);
}

TEST_F(CottonPickingOptimizerTest, EnergySavingsEmptyReturnsZero) {
    std::vector<geometry_msgs::msg::Point> pts;
    double savings = CottonPickingOptimizer::estimateEnergySavings(pts, Strategy::HIERARCHICAL);
    EXPECT_DOUBLE_EQ(savings, 0.0);
}

// ===================================================================
// 3.7  Edge cases
// ===================================================================

TEST_F(CottonPickingOptimizerTest, EmptyVectorAllStrategies) {
    for (auto strategy : {Strategy::NONE, Strategy::PHI_SWEEP, Strategy::HIERARCHICAL,
                          Strategy::NEAREST_FIRST, Strategy::RASTER_SCAN}) {
        std::vector<geometry_msgs::msg::Point> pts;
        CottonPickingOptimizer::optimizePickingOrder(pts, strategy);
        EXPECT_TRUE(pts.empty()) << "Strategy should handle empty vector";
    }
}

TEST_F(CottonPickingOptimizerTest, SinglePointAllStrategies) {
    auto original = makePoint(1.0, 2.0, 3.0);
    for (auto strategy : {Strategy::NONE, Strategy::PHI_SWEEP, Strategy::HIERARCHICAL,
                          Strategy::NEAREST_FIRST, Strategy::RASTER_SCAN}) {
        std::vector<geometry_msgs::msg::Point> pts = { original };
        CottonPickingOptimizer::optimizePickingOrder(pts, strategy);
        ASSERT_EQ(pts.size(), 1u);
        EXPECT_DOUBLE_EQ(pts[0].x, original.x);
        EXPECT_DOUBLE_EQ(pts[0].y, original.y);
        EXPECT_DOUBLE_EQ(pts[0].z, original.z);
    }
}

TEST_F(CottonPickingOptimizerTest, IdenticalPositions) {
    std::vector<geometry_msgs::msg::Point> pts = {
        makePoint(1.0, 1.0, 1.0),
        makePoint(1.0, 1.0, 1.0),
        makePoint(1.0, 1.0, 1.0),
    };

    for (auto strategy : {Strategy::PHI_SWEEP, Strategy::HIERARCHICAL,
                          Strategy::NEAREST_FIRST, Strategy::RASTER_SCAN}) {
        auto copy = pts;
        CottonPickingOptimizer::optimizePickingOrder(copy, strategy);
        ASSERT_EQ(copy.size(), 3u) << "Strategy must preserve count for identical points";
        for (const auto& p : copy) {
            EXPECT_DOUBLE_EQ(p.x, 1.0);
            EXPECT_DOUBLE_EQ(p.y, 1.0);
            EXPECT_DOUBLE_EQ(p.z, 1.0);
        }
    }
}

TEST_F(CottonPickingOptimizerTest, PositionsAtSamePhiAngle) {
    // All points on the same radial line (same phi) but different r/theta.
    std::vector<geometry_msgs::msg::Point> pts = {
        makePoint(3.0, 3.0, 2.0),
        makePoint(1.0, 1.0, 0.5),
        makePoint(2.0, 2.0, 1.0),
    };

    // PHI_SWEEP: all phis are equal (pi/4), order is implementation-defined
    // but must still contain all points.
    auto copy = pts;
    CottonPickingOptimizer::optimizePickingOrder(copy, Strategy::PHI_SWEEP);
    EXPECT_EQ(copy.size(), 3u);

    // HIERARCHICAL: same phi zone, so should sort by theta ascending.
    copy = pts;
    CottonPickingOptimizer::optimizePickingOrder(copy, Strategy::HIERARCHICAL, 0.0, 0.05);
    for (size_t i = 1; i < copy.size(); ++i) {
        EXPECT_LE(theta(copy[i - 1]), theta(copy[i]) + 1e-9)
            << "Within same phi zone, theta should be ascending";
    }
}

TEST_F(CottonPickingOptimizerTest, TwoPointsSwapped) {
    // Two-element case: phi_sweep should swap if needed.
    std::vector<geometry_msgs::msg::Point> pts = {
        makePoint(0.0, 1.0, 0.0),   // phi = pi/2
        makePoint(1.0, 0.0, 0.0),   // phi = 0
    };

    CottonPickingOptimizer::optimizePickingOrder(pts, Strategy::PHI_SWEEP);

    EXPECT_NEAR(phi(pts[0]), 0.0,        1e-9);
    EXPECT_NEAR(phi(pts[1]), M_PI / 2.0, 1e-9);
}

TEST_F(CottonPickingOptimizerTest, PointAtOriginDoesNotCrash) {
    // Origin has undefined atan2(0,0) = 0 in most implementations.
    std::vector<geometry_msgs::msg::Point> pts = {
        makePoint(0.0, 0.0, 0.0),
        makePoint(1.0, 1.0, 1.0),
    };

    for (auto strategy : {Strategy::PHI_SWEEP, Strategy::HIERARCHICAL,
                          Strategy::NEAREST_FIRST, Strategy::RASTER_SCAN}) {
        auto copy = pts;
        EXPECT_NO_THROW(
            CottonPickingOptimizer::optimizePickingOrder(copy, strategy))
            << "Strategy must not crash with origin point";
        EXPECT_EQ(copy.size(), 2u);
    }
}

// ===================================================================
// 3.8  PointStamped overload consistency
// ===================================================================

TEST_F(CottonPickingOptimizerTest, PointStampedProducesSameOrderAsPoint) {
    auto point_vec = makeSpreadPoints();

    // Build matching PointStamped vector.
    std::vector<geometry_msgs::msg::PointStamped> stamped_vec;
    for (const auto& p : point_vec) {
        stamped_vec.push_back(makePointStamped(p.x, p.y, p.z));
    }

    for (auto strategy : {Strategy::NONE, Strategy::PHI_SWEEP, Strategy::HIERARCHICAL,
                          Strategy::NEAREST_FIRST, Strategy::RASTER_SCAN}) {
        auto pts = point_vec;
        auto stamped = stamped_vec;

        CottonPickingOptimizer::optimizePickingOrder(pts, strategy, 0.0, 0.05);
        CottonPickingOptimizer::optimizePickingOrder(stamped, strategy, 0.0, 0.05);

        ASSERT_EQ(pts.size(), stamped.size())
            << "Size mismatch for strategy " << static_cast<int>(strategy);

        for (size_t i = 0; i < pts.size(); ++i) {
            EXPECT_DOUBLE_EQ(pts[i].x, stamped[i].point.x)
                << "X mismatch at index " << i
                << " for strategy " << static_cast<int>(strategy);
            EXPECT_DOUBLE_EQ(pts[i].y, stamped[i].point.y)
                << "Y mismatch at index " << i
                << " for strategy " << static_cast<int>(strategy);
            EXPECT_DOUBLE_EQ(pts[i].z, stamped[i].point.z)
                << "Z mismatch at index " << i
                << " for strategy " << static_cast<int>(strategy);
        }
    }
}

TEST_F(CottonPickingOptimizerTest, PointStampedPreservesHeader) {
    std::vector<geometry_msgs::msg::PointStamped> stamped = {
        makePointStamped(0.0, 1.0, 0.0, "camera_link"),
        makePointStamped(1.0, 0.0, 0.0, "camera_link"),
    };

    CottonPickingOptimizer::optimizePickingOrder(stamped, Strategy::PHI_SWEEP);

    // Headers should still be present (frame_id is not cleared).
    for (const auto& ps : stamped) {
        EXPECT_EQ(ps.header.frame_id, "camera_link");
    }
}

TEST_F(CottonPickingOptimizerTest, PointStampedEmptyVector) {
    std::vector<geometry_msgs::msg::PointStamped> stamped;
    CottonPickingOptimizer::optimizePickingOrder(stamped, Strategy::HIERARCHICAL);
    EXPECT_TRUE(stamped.empty());
}

TEST_F(CottonPickingOptimizerTest, PointStampedSingleElement) {
    std::vector<geometry_msgs::msg::PointStamped> stamped = {
        makePointStamped(1.0, 2.0, 3.0, "base_link"),
    };
    CottonPickingOptimizer::optimizePickingOrder(stamped, Strategy::HIERARCHICAL);
    ASSERT_EQ(stamped.size(), 1u);
    EXPECT_DOUBLE_EQ(stamped[0].point.x, 1.0);
    EXPECT_DOUBLE_EQ(stamped[0].point.y, 2.0);
    EXPECT_DOUBLE_EQ(stamped[0].point.z, 3.0);
}

}  // namespace yanthra_move
