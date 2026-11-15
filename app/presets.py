"""Starting points offered in the tool. Values are tool inputs (form units: %, whole $, quarters). Base is always $12."""

# Inputs:  none
# Outputs: PRESETS and STATUS_QUO (imported by app.py)

STATUS_QUO = {"label": "Today's policy (2019)", "values": {
    "offer_share_high": 25, "discount_high": 3, "offer_share_low": 25, "discount_low": 3,
    "lapsed_get_offers": True, "new_member_discount": 3, "established_member_discount": 3, "random_depths": True,
    "horizon_quarters": 12, "discount_rate_pct": 0}}

RECOMMENDED = {"label": "Recommended", "values": {
    "offer_share_high": 100, "discount_high": 5, "offer_share_low": 100, "discount_low": 5,
    "lapsed_get_offers": False, "new_member_discount": 5, "established_member_discount": 1, "random_depths": False,
    "horizon_quarters": 12, "discount_rate_pct": 0}}

SAME_DISCOUNT_FOR_ALL_MEMBERS = {"label": "Same $2 discount for all members", "values": {
    **RECOMMENDED["values"], "new_member_discount": 2, "established_member_discount": 2}}

SMALLEST_DISCOUNTS = {"label": "No intro offer, $1 off for members", "values": {
    **RECOMMENDED["values"], "offer_share_high": 0, "discount_high": 0, "offer_share_low": 0, "discount_low": 0,
    "new_member_discount": 1, "established_member_discount": 1}}

PRESETS = {"recommended": RECOMMENDED, "status_quo": STATUS_QUO, "same_discount": SAME_DISCOUNT_FOR_ALL_MEMBERS,
           "smallest_discounts": SMALLEST_DISCOUNTS}
