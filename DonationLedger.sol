// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title DonationLedger
/// @notice Sổ cái công khai: ghi lại mỗi khoản quyên góp (tiền vào) đã được MoMo xác nhận
///         và mỗi khoản chi của quỹ (tiền ra). Dữ liệu đã ghi thì không sửa/xóa được.
/// @dev    Tiền thật đi qua MoMo, KHÔNG đi qua hợp đồng này. Hợp đồng chỉ lưu bằng chứng.
///         Không lưu tên / số điện thoại người quyên góp.
contract DonationLedger {
    address public owner;
    mapping(address => bool) public recorders; // backend được phép ghi
    mapping(string => bool) public usedMomoTxn; // chống ghi trùng 1 giao dịch MoMo

    struct Donation {
        string fundId;
        uint256 amount; // VND
        string momoTxnId;
        uint256 timestamp;
    }

    struct Disbursement {
        string fundId;
        uint256 amount; // VND
        string purpose;
        bytes32 evidenceHash; // hash của chứng từ (ảnh hóa đơn, biên bản...)
        uint256 timestamp;
    }

    Donation[] public donations;
    Disbursement[] public disbursements;
    mapping(string => uint256) public totalIn;
    mapping(string => uint256) public totalOut;

    event DonationRecorded(uint256 indexed id, string fundId, uint256 amount, string momoTxnId, uint256 timestamp);
    event DisbursementRecorded(uint256 indexed id, string fundId, uint256 amount, string purpose, bytes32 evidenceHash, uint256 timestamp);
    event RecorderChanged(address recorder, bool allowed);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    modifier onlyRecorder() {
        require(recorders[msg.sender], "not recorder");
        _;
    }

    constructor() {
        owner = msg.sender;
        recorders[msg.sender] = true;
        emit RecorderChanged(msg.sender, true);
    }

    function setRecorder(address recorder, bool allowed) external onlyOwner {
        recorders[recorder] = allowed;
        emit RecorderChanged(recorder, allowed);
    }

    /// @notice Ghi một khoản quyên góp sau khi MoMo báo thanh toán thành công.
    function recordDonation(string calldata fundId, uint256 amount, string calldata momoTxnId)
        external
        onlyRecorder
        returns (uint256 id)
    {
        require(amount > 0, "amount = 0");
        require(!usedMomoTxn[momoTxnId], "txn already recorded");
        usedMomoTxn[momoTxnId] = true;
        donations.push(Donation(fundId, amount, momoTxnId, block.timestamp));
        totalIn[fundId] += amount;
        id = donations.length - 1;
        emit DonationRecorded(id, fundId, amount, momoTxnId, block.timestamp);
    }

    /// @notice Quỹ ghi một khoản chi kèm hash chứng từ.
    function recordDisbursement(string calldata fundId, uint256 amount, string calldata purpose, bytes32 evidenceHash)
        external
        onlyRecorder
        returns (uint256 id)
    {
        require(amount > 0, "amount = 0");
        disbursements.push(Disbursement(fundId, amount, purpose, evidenceHash, block.timestamp));
        totalOut[fundId] += amount;
        id = disbursements.length - 1;
        emit DisbursementRecorded(id, fundId, amount, purpose, evidenceHash, block.timestamp);
    }

    function donationCount() external view returns (uint256) {
        return donations.length;
    }

    function disbursementCount() external view returns (uint256) {
        return disbursements.length;
    }
}
