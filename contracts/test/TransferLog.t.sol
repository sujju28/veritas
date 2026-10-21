// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {TransferLog} from "../src/TransferLog.sol";

contract TransferLogTest is Test {
    TransferLog internal transferLog;
    address internal admin = address(this);
    address internal writer = address(0xA11CE);
    address internal stranger = address(0xB0B);

    bytes32 internal acct1 = "acct-0001";
    bytes32 internal acct2 = "acct-0002";
    bytes32 internal bankA = "BANK_A";
    bytes32 internal bankB = "BANK_B";
    uint64 internal openedAt1 = 1700000000;
    uint64 internal openedAt2 = 1700000100;

    bytes32 internal txId1 = "txn-000001";
    bytes32 internal txId2 = "txn-000002";
    uint128 internal amount1 = 50000;
    uint128 internal amount2 = 75000;
    uint64 internal time1 = 1700000500;
    uint64 internal time2 = 1700000600;

    function setUp() public {
        transferLog = new TransferLog(writer);
    }

    function test_register_accounts_and_replay_idempotent() public {
        bytes32[] memory accounts = new bytes32[](2);
        accounts[0] = acct1;
        accounts[1] = acct2;

        bytes32[] memory banks = new bytes32[](2);
        banks[0] = bankA;
        banks[1] = bankB;

        uint64[] memory openedAts = new uint64[](2);
        openedAts[0] = openedAt1;
        openedAts[1] = openedAt2;

        vm.expectEmit(true, false, true, true);
        emit TransferLog.AccountRegistered(acct1, bankA, openedAt1, writer, block.number);
        vm.expectEmit(true, false, true, true);
        emit TransferLog.AccountRegistered(acct2, bankB, openedAt2, writer, block.number);

        vm.prank(writer);
        transferLog.registerAccounts(accounts, banks, openedAts);

        (bool exists, bytes32 digest, uint64 bNum, uint64 ts) = transferLog.getAccount(acct1);
        assertTrue(exists);
        assertEq(digest, keccak256(abi.encode(bankA, openedAt1)));
        assertEq(bNum, block.number);
        assertEq(ts, block.timestamp);

        // Replay same batch: idempotent, emits 0 events
        vm.recordLogs();
        vm.prank(writer);
        transferLog.registerAccounts(accounts, banks, openedAts);
        assertEq(vm.getRecordedLogs().length, 0);
    }

    function test_register_account_conflict_reverts() public {
        bytes32[] memory accounts = new bytes32[](1);
        accounts[0] = acct1;
        bytes32[] memory banks = new bytes32[](1);
        banks[0] = bankA;
        uint64[] memory openedAts = new uint64[](1);
        openedAts[0] = openedAt1;

        vm.prank(writer);
        transferLog.registerAccounts(accounts, banks, openedAts);

        // Try registering with different bank
        banks[0] = bankB;
        bytes32 oldDigest = keccak256(abi.encode(bankA, openedAt1));
        bytes32 newDigest = keccak256(abi.encode(bankB, openedAt1));

        vm.expectRevert(
            abi.encodeWithSelector(TransferLog.AccountMismatch.selector, oldDigest, newDigest)
        );
        vm.prank(writer);
        transferLog.registerAccounts(accounts, banks, openedAts);
    }

    function test_record_transfers_and_replay_idempotent() public {
        bytes32[] memory txIds = new bytes32[](2);
        txIds[0] = txId1;
        txIds[1] = txId2;

        bytes32[] memory froms = new bytes32[](2);
        froms[0] = acct1;
        froms[1] = acct2;

        bytes32[] memory tos = new bytes32[](2);
        tos[0] = acct2;
        tos[1] = acct1;

        uint128[] memory amounts = new uint128[](2);
        amounts[0] = amount1;
        amounts[1] = amount2;

        uint64[] memory times = new uint64[](2);
        times[0] = time1;
        times[1] = time2;

        vm.expectEmit(true, true, true, true);
        emit TransferLog.TransferRecorded(
            txId1, acct1, acct2, amount1, time1, writer, block.number
        );
        vm.expectEmit(true, true, true, true);
        emit TransferLog.TransferRecorded(
            txId2, acct2, acct1, amount2, time2, writer, block.number
        );

        vm.prank(writer);
        transferLog.recordTransfers(txIds, froms, tos, amounts, times);

        (bool exists, bytes32 digest, uint64 bNum, uint64 ts) = transferLog.getTransfer(txId1);
        assertTrue(exists);
        assertEq(digest, keccak256(abi.encode(acct1, acct2, amount1, time1)));
        assertEq(bNum, block.number);
        assertEq(ts, block.timestamp);

        // Replay same batch: idempotent, emits 0 events (ONC-01)
        vm.recordLogs();
        vm.prank(writer);
        transferLog.recordTransfers(txIds, froms, tos, amounts, times);
        assertEq(vm.getRecordedLogs().length, 0);
    }

    function test_record_transfer_conflict_reverts() public {
        bytes32[] memory txIds = new bytes32[](1);
        txIds[0] = txId1;
        bytes32[] memory froms = new bytes32[](1);
        froms[0] = acct1;
        bytes32[] memory tos = new bytes32[](1);
        tos[0] = acct2;
        uint128[] memory amounts = new uint128[](1);
        amounts[0] = amount1;
        uint64[] memory times = new uint64[](1);
        times[0] = time1;

        vm.prank(writer);
        transferLog.recordTransfers(txIds, froms, tos, amounts, times);

        // Try recording with different amount
        amounts[0] = amount1 + 1000;
        bytes32 oldDigest = keccak256(abi.encode(acct1, acct2, amount1, time1));
        bytes32 newDigest = keccak256(abi.encode(acct1, acct2, amount1 + 1000, time1));

        vm.expectRevert(
            abi.encodeWithSelector(TransferLog.TransferMismatch.selector, oldDigest, newDigest)
        );
        vm.prank(writer);
        transferLog.recordTransfers(txIds, froms, tos, amounts, times);
    }

    function test_validations_mirror_sqlite_checks() public {
        bytes32[] memory txIds = new bytes32[](1);
        txIds[0] = txId1;
        bytes32[] memory froms = new bytes32[](1);
        froms[0] = acct1;
        bytes32[] memory tos = new bytes32[](1);
        tos[0] = acct1; // self transfer!
        uint128[] memory amounts = new uint128[](1);
        amounts[0] = amount1;
        uint64[] memory times = new uint64[](1);
        times[0] = time1;

        // Self transfer
        vm.expectRevert(abi.encodeWithSelector(TransferLog.SelfTransfer.selector, acct1));
        vm.prank(writer);
        transferLog.recordTransfers(txIds, froms, tos, amounts, times);

        // Zero amount
        tos[0] = acct2;
        amounts[0] = 0;
        vm.expectRevert(TransferLog.ZeroAmount.selector);
        vm.prank(writer);
        transferLog.recordTransfers(txIds, froms, tos, amounts, times);

        // Zero ID
        amounts[0] = amount1;
        txIds[0] = bytes32(0);
        vm.expectRevert(TransferLog.ZeroId.selector);
        vm.prank(writer);
        transferLog.recordTransfers(txIds, froms, tos, amounts, times);
    }

    function test_empty_or_length_mismatch_reverts() public {
        bytes32[] memory empty = new bytes32[](0);
        uint64[] memory emptyTime = new uint64[](0);

        vm.expectRevert(TransferLog.BatchEmpty.selector);
        vm.prank(writer);
        transferLog.registerAccounts(empty, empty, emptyTime);

        bytes32[] memory one = new bytes32[](1);
        one[0] = acct1;
        bytes32[] memory two = new bytes32[](2);
        two[0] = bankA;
        two[1] = bankB;

        vm.expectRevert(TransferLog.ArrayLengthMismatch.selector);
        vm.prank(writer);
        transferLog.registerAccounts(one, two, emptyTime);
    }

    function test_unauthorized_writer_reverts() public {
        bytes32[] memory accounts = new bytes32[](1);
        accounts[0] = acct1;
        bytes32[] memory banks = new bytes32[](1);
        banks[0] = bankA;
        uint64[] memory openedAts = new uint64[](1);
        openedAts[0] = openedAt1;

        vm.expectRevert(TransferLog.NotWriter.selector);
        vm.prank(stranger);
        transferLog.registerAccounts(accounts, banks, openedAts);
    }

    function test_admin_grants_and_revokes_writer() public {
        vm.prank(stranger);
        vm.expectRevert(TransferLog.NotAdmin.selector);
        transferLog.grantWriter(stranger);

        transferLog.grantWriter(stranger);
        assertTrue(transferLog.writers(stranger));

        transferLog.revokeWriter(stranger);
        assertFalse(transferLog.writers(stranger));
    }
}
