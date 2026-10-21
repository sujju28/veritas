// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title TransferLog
/// @notice Records financial accounts and transfers on a local Anvil chain.
/// @dev Anvil is a development EVM. Replay is idempotent per account and transfer id.
///      Labels and scenario data are NEVER stored on-chain.
contract TransferLog {
    struct AccountEntry {
        bool exists;
        bytes32 digest;
        uint64 blockNumber;
        uint64 timestamp;
    }

    struct TransferEntry {
        bool exists;
        bytes32 digest;
        uint64 blockNumber;
        uint64 timestamp;
    }

    uint256 public constant MAX_BATCH = 500;

    address public admin;
    mapping(address => bool) public writers;
    mapping(bytes32 => AccountEntry) private accounts;
    mapping(bytes32 => TransferEntry) private transfers;

    event WriterGranted(address indexed writer);
    event WriterRevoked(address indexed writer);

    event AccountRegistered(
        bytes32 indexed account,
        bytes32 bank,
        uint64 openedAt,
        address indexed sender,
        uint256 blockNumber
    );

    event TransferRecorded(
        bytes32 indexed txId,
        bytes32 indexed from,
        bytes32 indexed to,
        uint128 amountMinor,
        uint64 eventTime,
        address sender,
        uint256 blockNumber
    );

    error ZeroAddress();
    error NotAdmin();
    error NotWriter();
    error ArrayLengthMismatch();
    error BatchEmpty();
    error BatchTooLarge(uint256 size, uint256 max);
    error ZeroId();
    error SelfTransfer(bytes32 account);
    error ZeroAmount();
    error AccountMismatch(bytes32 storedDigest, bytes32 submittedDigest);
    error TransferMismatch(bytes32 storedDigest, bytes32 submittedDigest);

    constructor(address initialWriter) {
        if (initialWriter == address(0)) revert ZeroAddress();
        admin = msg.sender;
        writers[initialWriter] = true;
        emit WriterGranted(initialWriter);
    }

    function grantWriter(address writer) external {
        if (msg.sender != admin) revert NotAdmin();
        if (writer == address(0)) revert ZeroAddress();
        writers[writer] = true;
        emit WriterGranted(writer);
    }

    function revokeWriter(address writer) external {
        if (msg.sender != admin) revert NotAdmin();
        writers[writer] = false;
        emit WriterRevoked(writer);
    }

    function registerAccounts(
        bytes32[] calldata accountIds,
        bytes32[] calldata bankIds,
        uint64[] calldata openedAts
    ) external {
        if (!writers[msg.sender]) revert NotWriter();
        uint256 len = accountIds.length;
        if (len == 0) revert BatchEmpty();
        if (len > MAX_BATCH) revert BatchTooLarge(len, MAX_BATCH);
        if (len != bankIds.length || len != openedAts.length) revert ArrayLengthMismatch();

        for (uint256 i = 0; i < len; i++) {
            bytes32 account = accountIds[i];
            bytes32 bank = bankIds[i];
            uint64 openedAt = openedAts[i];

            if (account == bytes32(0) || bank == bytes32(0)) revert ZeroId();

            bytes32 digest = keccak256(abi.encode(bank, openedAt));
            AccountEntry storage existing = accounts[account];
            if (existing.exists) {
                if (existing.digest != digest) {
                    revert AccountMismatch(existing.digest, digest);
                }
                continue;
            }

            accounts[account] = AccountEntry({
                exists: true,
                digest: digest,
                blockNumber: uint64(block.number),
                timestamp: uint64(block.timestamp)
            });

            emit AccountRegistered(account, bank, openedAt, msg.sender, block.number);
        }
    }

    function recordTransfers(
        bytes32[] calldata txIds,
        bytes32[] calldata froms,
        bytes32[] calldata tos,
        uint128[] calldata amountsMinor,
        uint64[] calldata eventTimes
    ) external {
        if (!writers[msg.sender]) revert NotWriter();
        uint256 len = txIds.length;
        if (len == 0) revert BatchEmpty();
        if (len > MAX_BATCH) revert BatchTooLarge(len, MAX_BATCH);
        if (
            len != froms.length ||
            len != tos.length ||
            len != amountsMinor.length ||
            len != eventTimes.length
        ) {
            revert ArrayLengthMismatch();
        }

        for (uint256 i = 0; i < len; i++) {
            bytes32 txId = txIds[i];
            bytes32 from = froms[i];
            bytes32 to = tos[i];
            uint128 amount = amountsMinor[i];
            uint64 eventTime = eventTimes[i];

            if (txId == bytes32(0) || from == bytes32(0) || to == bytes32(0)) revert ZeroId();
            if (from == to) revert SelfTransfer(from);
            if (amount == 0) revert ZeroAmount();

            bytes32 digest = keccak256(abi.encode(from, to, amount, eventTime));
            TransferEntry storage existing = transfers[txId];
            if (existing.exists) {
                if (existing.digest != digest) {
                    revert TransferMismatch(existing.digest, digest);
                }
                continue;
            }

            transfers[txId] = TransferEntry({
                exists: true,
                digest: digest,
                blockNumber: uint64(block.number),
                timestamp: uint64(block.timestamp)
            });

            emit TransferRecorded(txId, from, to, amount, eventTime, msg.sender, block.number);
        }
    }

    function getAccount(bytes32 account)
        external
        view
        returns (bool exists, bytes32 digest, uint64 blockNumber, uint64 timestamp)
    {
        AccountEntry storage item = accounts[account];
        return (item.exists, item.digest, item.blockNumber, item.timestamp);
    }

    function getTransfer(bytes32 txId)
        external
        view
        returns (bool exists, bytes32 digest, uint64 blockNumber, uint64 timestamp)
    {
        TransferEntry storage item = transfers[txId];
        return (item.exists, item.digest, item.blockNumber, item.timestamp);
    }
}
