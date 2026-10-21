// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {RulesetRegistry} from "../src/RulesetRegistry.sol";

contract RulesetRegistryTest is Test {
    RulesetRegistry internal registry;
    address internal admin = address(this);
    address internal stranger = address(0xB0B);

    bytes32 internal key = sha256("VERITAS:RULESET:rules-v1");
    bytes32 internal manifestHash = sha256("manifest-bytes-v1");
    bytes32 internal otherHash = sha256("manifest-bytes-v2");

    function setUp() public {
        registry = new RulesetRegistry();
    }

    function test_register_stores_entry_and_emits_event() public {
        vm.expectEmit(true, false, true, true);
        emit RulesetRegistry.RulesetRegistered(key, manifestHash, admin, block.number);
        registry.register(key, manifestHash);

        (
            bool exists,
            bytes32 storedHash,
            bool deprecated,
            address sender,
            uint64 blockNumber,
            uint64 timestamp
        ) = registry.getRuleset(key);

        assertTrue(exists);
        assertEq(storedHash, manifestHash);
        assertFalse(deprecated);
        assertEq(sender, admin);
        assertEq(blockNumber, block.number);
        assertEq(timestamp, block.timestamp);
    }

    function test_same_hash_is_no_op_and_emits_nothing() public {
        registry.register(key, manifestHash);

        vm.recordLogs();
        registry.register(key, manifestHash);
        assertEq(vm.getRecordedLogs().length, 0);

        (bool exists, bytes32 storedHash,,,,) = registry.getRuleset(key);
        assertTrue(exists);
        assertEq(storedHash, manifestHash);
    }

    function test_different_hash_for_same_key_reverts() public {
        registry.register(key, manifestHash);

        vm.expectRevert(
            abi.encodeWithSelector(
                RulesetRegistry.ManifestMismatch.selector,
                manifestHash,
                otherHash
            )
        );
        registry.register(key, otherHash);
    }

    function test_non_admin_cannot_register() public {
        vm.prank(stranger);
        vm.expectRevert(RulesetRegistry.NotAdmin.selector);
        registry.register(key, manifestHash);
    }

    function test_zero_key_and_zero_digest_revert() public {
        vm.expectRevert(RulesetRegistry.ZeroKey.selector);
        registry.register(bytes32(0), manifestHash);

        vm.expectRevert(RulesetRegistry.ZeroDigest.selector);
        registry.register(key, bytes32(0));
    }

    function test_unknown_ruleset_is_absent() public view {
        (
            bool exists,
            bytes32 storedHash,
            bool deprecated,
            address sender,
            uint64 blockNumber,
            uint64 timestamp
        ) = registry.getRuleset(sha256("missing"));

        assertFalse(exists);
        assertEq(storedHash, bytes32(0));
        assertFalse(deprecated);
        assertEq(sender, address(0));
        assertEq(blockNumber, 0);
        assertEq(timestamp, 0);
    }

    function test_deprecate_succeeds_and_emits_event() public {
        registry.register(key, manifestHash);

        vm.expectEmit(true, false, true, true);
        emit RulesetRegistry.RulesetDeprecated(key, admin, block.number);
        registry.deprecate(key);

        (,, bool deprecated,,,) = registry.getRuleset(key);
        assertTrue(deprecated);

        // Re-deprecating is idempotent no-op
        vm.recordLogs();
        registry.deprecate(key);
        assertEq(vm.getRecordedLogs().length, 0);
    }

    function test_deprecate_nonexistent_reverts() public {
        vm.expectRevert(
            abi.encodeWithSelector(RulesetRegistry.RulesetNotFound.selector, key)
        );
        registry.deprecate(key);
    }

    function test_non_admin_cannot_deprecate() public {
        registry.register(key, manifestHash);

        vm.prank(stranger);
        vm.expectRevert(RulesetRegistry.NotAdmin.selector);
        registry.deprecate(key);
    }
}
