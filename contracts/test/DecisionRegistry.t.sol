// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {DecisionRegistry} from "../src/DecisionRegistry.sol";

contract DecisionRegistryTest is Test {
    DecisionRegistry internal registry;
    address internal writer = address(0xA11CE);
    address internal stranger = address(0xB0B);

    bytes32 internal key = keccak256("decision-key");
    bytes32 internal digest = keccak256("evidence-digest");

    function setUp() public {
        registry = new DecisionRegistry(writer);
    }

    function test_anchor_stores_commitment_and_emits_event() public {
        vm.expectEmit(true, true, false, true);
        emit DecisionRegistry.DecisionAnchored(key, digest, writer, block.number);
        vm.prank(writer);
        registry.anchorDecision(key, digest);

        (bool exists, bytes32 stored, address sender, uint64 blockNumber, uint64 timestamp) =
            registry.getDecision(key);
        assertTrue(exists);
        assertEq(stored, digest);
        assertEq(sender, writer);
        assertEq(blockNumber, block.number);
        assertEq(timestamp, block.timestamp);
    }

    function test_same_digest_is_unchanged_and_emits_nothing() public {
        vm.startPrank(writer);
        registry.anchorDecision(key, digest);
        vm.recordLogs();
        registry.anchorDecision(key, digest);
        vm.stopPrank();
        assertEq(vm.getRecordedLogs().length, 0);

        (bool exists, bytes32 stored, address sender,,) = registry.getDecision(key);
        assertTrue(exists);
        assertEq(stored, digest);
        assertEq(sender, writer);
    }

    function test_different_digest_reverts() public {
        vm.startPrank(writer);
        registry.anchorDecision(key, digest);
        vm.expectRevert(
            abi.encodeWithSelector(
                DecisionRegistry.DigestMismatch.selector, digest, keccak256("other")
            )
        );
        registry.anchorDecision(key, keccak256("other"));
        vm.stopPrank();
    }

    function test_unauthorized_address_reverts() public {
        vm.prank(stranger);
        vm.expectRevert(DecisionRegistry.NotAnchorWriter.selector);
        registry.anchorDecision(key, digest);
    }

    function test_revoked_writer_reverts() public {
        registry.revokeAnchorWriter(writer);
        vm.prank(writer);
        vm.expectRevert(DecisionRegistry.NotAnchorWriter.selector);
        registry.anchorDecision(key, digest);
    }

    function test_unknown_key_is_absent() public view {
        (bool exists, bytes32 stored, address sender, uint64 blockNumber, uint64 timestamp) =
            registry.getDecision(keccak256("missing"));
        assertFalse(exists);
        assertEq(stored, bytes32(0));
        assertEq(sender, address(0));
        assertEq(blockNumber, 0);
        assertEq(timestamp, 0);
    }

    function test_zero_key_and_zero_digest_revert() public {
        vm.startPrank(writer);
        vm.expectRevert(DecisionRegistry.ZeroKey.selector);
        registry.anchorDecision(bytes32(0), digest);
        vm.expectRevert(DecisionRegistry.ZeroDigest.selector);
        registry.anchorDecision(key, bytes32(0));
        vm.stopPrank();
    }

    function test_only_admin_grants_and_revokes() public {
        vm.prank(stranger);
        vm.expectRevert(DecisionRegistry.NotAdmin.selector);
        registry.grantAnchorWriter(stranger);

        registry.grantAnchorWriter(stranger);
        assertTrue(registry.anchorWriters(stranger));
        vm.prank(stranger);
        registry.anchorDecision(key, digest);

        registry.revokeAnchorWriter(stranger);
        assertFalse(registry.anchorWriters(stranger));
    }

    function test_zero_writer_is_rejected() public {
        vm.expectRevert(DecisionRegistry.ZeroAddress.selector);
        new DecisionRegistry(address(0));
        vm.expectRevert(DecisionRegistry.ZeroAddress.selector);
        registry.grantAnchorWriter(address(0));
    }
}
