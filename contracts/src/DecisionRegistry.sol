// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title DecisionRegistry
/// @notice Stores an opaque decision key and an evidence digest on a local Anvil chain.
/// @dev Anvil is a resettable development EVM. It is not a permissioned QBFT ledger.
///      A matching digest is a no-op. A different digest for the same key reverts.
contract DecisionRegistry {
    struct Commitment {
        bool exists;
        bytes32 evidenceDigest;
        address sender;
        uint64 blockNumber;
        uint64 timestamp;
    }

    address public admin;
    mapping(address => bool) public anchorWriters;
    mapping(bytes32 => Commitment) private commitments;

    event AnchorWriterGranted(address indexed writer);
    event AnchorWriterRevoked(address indexed writer);
    event DecisionAnchored(
        bytes32 indexed key,
        bytes32 evidenceDigest,
        address indexed sender,
        uint256 blockNumber
    );

    error ZeroAddress();
    error ZeroKey();
    error ZeroDigest();
    error NotAdmin();
    error NotAnchorWriter();
    error DigestMismatch(bytes32 storedDigest, bytes32 submittedDigest);

    constructor(address initialWriter) {
        if (initialWriter == address(0)) revert ZeroAddress();
        admin = msg.sender;
        anchorWriters[initialWriter] = true;
        emit AnchorWriterGranted(initialWriter);
    }

    function grantAnchorWriter(address writer) external {
        if (msg.sender != admin) revert NotAdmin();
        if (writer == address(0)) revert ZeroAddress();
        anchorWriters[writer] = true;
        emit AnchorWriterGranted(writer);
    }

    function revokeAnchorWriter(address writer) external {
        if (msg.sender != admin) revert NotAdmin();
        anchorWriters[writer] = false;
        emit AnchorWriterRevoked(writer);
    }

    function anchorDecision(bytes32 key, bytes32 evidenceDigest) external {
        if (!anchorWriters[msg.sender]) revert NotAnchorWriter();
        if (key == bytes32(0)) revert ZeroKey();
        if (evidenceDigest == bytes32(0)) revert ZeroDigest();
        Commitment storage existing = commitments[key];
        if (existing.exists) {
            if (existing.evidenceDigest != evidenceDigest) {
                revert DigestMismatch(existing.evidenceDigest, evidenceDigest);
            }
            return;
        }
        commitments[key] = Commitment({
            exists: true,
            evidenceDigest: evidenceDigest,
            sender: msg.sender,
            blockNumber: uint64(block.number),
            timestamp: uint64(block.timestamp)
        });
        emit DecisionAnchored(key, evidenceDigest, msg.sender, block.number);
    }

    function getDecision(bytes32 key)
        external
        view
        returns (
            bool exists,
            bytes32 evidenceDigest,
            address sender,
            uint64 blockNumber,
            uint64 timestamp
        )
    {
        Commitment storage item = commitments[key];
        return (item.exists, item.evidenceDigest, item.sender, item.blockNumber, item.timestamp);
    }
}
