// Copyright (c) rAthena Dev Teams - Licensed under GNU GPL
#include "stylist.hpp"

#include <cstring>
#include <random>
#include <unordered_map>

#include <common/showmsg.hpp>
#include <common/socket.hpp>
#include <common/timer.hpp>
#include <common/utilities.hpp>
#include "battle.hpp"
#include "chrif.hpp"
#include "clif.hpp"
#include "itemdb.hpp"
#include "log.hpp"
#include "npc.hpp"
#include "pc.hpp"
#include "pc_groups.hpp"

using namespace rathena;

// Stylist: appearance policy
bool stylist_body_allowed(uint16 job, uint32 body, uint8 sex) {
	if( body > UINT16_MAX ) return false;
	if( stylist::body_for_sex(static_cast<uint16>(body), sex) != body ) return false;
	if( job == body ) return true;
	if( !stylist::costume_access(job, battle_config.stylist_costume_jobs) ) return false;
	auto list = stylist_db.find(LOOK_BODY2);
	if( list != nullptr ) for( const auto& pair : list->entries ) {
		const auto& entry = pair.second;
		if( entry->required_job == job && entry->value == body &&
			(!entry->lineage_only || battle_config.stylist_class_lineage) &&
			(sex == SEX_BOTH || entry->required_sex == SEX_BOTH || entry->required_sex == sex) ) return true;
	}
	return false;
}
// End Stylist: appearance policy

// Stylist: UI
bool clif_stylist_open( map_session_data& sd, int32 data ){
#if PACKETVER < 20171122
	(void)data;
#endif
#if PACKETVER >= 20151202
	if( !battle_config.feature_stylist ) return false;
#if PACKETVER >= 20231220
	// npc_id is intentionally allowed: an NPC can open Stylist after close2.
	// pc_cant_act2 includes other windows and an outstanding durable purchase.
	if( pc_get_group_level( &sd ) < battle_config.stylist_min_group ||
		pc_isdead( &sd ) || pc_cant_act2( &sd ) || sd.chatID || !chrif_isconnected() ) return false;
#endif
	PACKET_ZC_UI_OPEN p = {};
	p.PacketType = HEADER_ZC_UI_OPEN;
	p.UIType = OUT_UI_STYLIST;
#if PACKETVER >= 20171122
	p.data = data;
#endif
	sd.state.stylist_open = true;
	clif_send( &p, sizeof( p ), &sd, SELF );
	return true;
#else
	(void)sd;
	return false;
#endif
}
// End Stylist: UI

// Stylist: purchase
#if PACKETVER >= 20231220
void clif_stylist_buy_modern( int32 fd, map_session_data* sd ){
	if( sd == nullptr ) return;
	auto fail = [&]( const char* reason ){
		if( battle_config.stylist_packet_debug ) ShowInfo( "Stylist rejected char=%d: %s\n", sd->status.char_id, reason );
		clif_stylist_response( sd, true );
	};
	if( !battle_config.feature_stylist || !sd->state.stylist_open || pc_get_group_level( sd ) < battle_config.stylist_min_group ||
		pc_isdead( sd ) || pc_cant_act2( sd, true ) || sd->chatID || sd->npc_id || !chrif_isconnected() ){
		fail( "session/state" ); return;
	}
	if( RFIFOREST( fd ) < 6 || RFIFOW( fd, 0 ) != HEADER_CZ_REQ_STYLE_CHANGE3 ){
		fail( "header" ); return;
	}
	const size_t size = RFIFOW( fd, 2 );
	if( size > RFIFOREST( fd ) ) { fail( "truncated packet" ); return; }
	const bool doram = ( sd->class_ & MAPID_FIRSTMASK ) == MAPID_SUMMONER;
	std::vector<stylist::Selection> selections;
	if( !stylist::decode( static_cast<const uint8_t*>( RFIFOP( fd, 0 ) ), size, doram, selections ) ){
		fail( "invalid selections" ); return;
	}
	static const _look looks[] = { LOOK_HAIR_COLOR, LOOK_HAIR, LOOK_CLOTHES_COLOR,
		LOOK_HEAD_TOP, LOOK_HEAD_MID, LOOK_HEAD_BOTTOM, LOOK_BODY2 };
	std::vector<std::shared_ptr<s_stylist_entry>> entries;
	std::vector<stylist::Cost> costs;
	int32 final_hair = sd->status.hair;
	int32 final_color = sd->status.hair_color;
	bool selected_color = false;
	struct mail_message mail = {};
	int32 attachments = 0;
	for( const auto& selection : selections ){
		if( battle_config.stylist_packet_debug ) ShowInfo( "Stylist char=%d action=%d index=%d\n", sd->status.char_id, selection.action, selection.index );
		const _look look = looks[selection.action == 9 ? 6 : selection.action];
		auto list = stylist_db.find( look );
		auto entry = list == nullptr ? nullptr : util::umap_find( list->entries, selection.index );
		if( entry == nullptr || ( entry->required_job >= 0 && entry->required_job != sd->status.class_ ) ||
			(entry->lineage_only && !battle_config.stylist_class_lineage) ||
			(entry->required_sex != SEX_BOTH && entry->required_sex != sd->status.sex) ){
			fail( "catalogue/job" ); return;
		}
		auto cost = doram ? entry->doram : entry->human;
		if( cost == nullptr ) { fail( "species unavailable" ); return; }
		if( look == LOOK_BODY2 && !stylist_body_allowed( sd->status.class_, entry->value, sd->status.sex ) ){
			fail( "body appearance" ); return;
		}
		if( ( look == LOOK_HAIR && ( entry->value < MIN_HAIR_STYLE || entry->value > MAX_HAIR_STYLE ) ) ||
			( look == LOOK_HAIR_COLOR && ( entry->value < MIN_HAIR_COLOR || entry->value > MAX_HAIR_COLOR ) ) ||
			( look == LOOK_CLOTHES_COLOR && ( entry->value < MIN_CLOTH_COLOR || entry->value > MAX_CLOTH_COLOR ) ) ){
			fail( "appearance limits" ); return;
		}
		if( look == LOOK_HAIR ) final_hair = entry->value;
		if( look == LOOK_HAIR_COLOR ) { final_color = entry->value; selected_color = true; }
		if( look == LOOK_HEAD_TOP || look == LOOK_HEAD_MID || look == LOOK_HEAD_BOTTOM ){
			// Fail the WHOLE purchase before charging if durable RODEX is disabled.
			if( !battle_config.stylist_accessory_mail || attachments >= MAIL_MAX_ITEM || !item_db.exists( entry->value ) ){
				fail( "accessory delivery not enabled" ); return;
			}
			auto& item = mail.item[attachments++];
			item.nameid = entry->value; item.amount = 1; item.identify = 1;
		}
		entries.push_back( entry );
		costs.push_back( {cost->price, cost->requiredItem, cost->requiredItemBox} );
	}
	bool reset_color = false;
	if( doram ){
		auto hairs = stylist_db.find( LOOK_HAIR );
		if( hairs != nullptr ) for( const auto& pair : hairs->entries ){
			const auto& hair = pair.second;
			if( hair->value == static_cast<uint32>( final_hair ) && hair->doram != nullptr && !hair->colorable_doram ){
				if( selected_color && final_color != 0 ) { fail( "hair cannot be colored" ); return; }
				reset_color = true;
			}
		}
	}
	std::map<uint32_t, uint32_t> stock;
	for( int32 i = 0; i < MAX_INVENTORY; ++i ){
		const auto& item = sd->inventory.u.items_inventory[i];
		if( item.nameid && item.amount > 0 && !item.equip && !item.equipSwitch && !item.expire_time && sd->inventory_data[i] != nullptr ) stock[item.nameid] += item.amount;
	}
	stylist::Payment payment;
	if( !stylist::plan_payment( costs, sd->status.zeny, stock, payment ) ) { fail( "insufficient aggregate payment" ); return; }
	// Resolve exact inventory slots before the first mutation. No event-loop yield
	// or script execution occurs between validation and the debits below.
	std::vector<std::pair<int32, int32>> debits;
	std::vector<struct item> refunds;
	for( const auto& required : payment.items ){
		uint32 left = required.second;
		for( int32 i = 0; i < MAX_INVENTORY && left; ++i ){
			const auto& item = sd->inventory.u.items_inventory[i];
			if( item.nameid != required.first || item.amount <= 0 || item.equip || item.equipSwitch || item.expire_time || sd->inventory_data[i] == nullptr ) continue;
			const uint32 take = std::min( left, static_cast<uint32>( item.amount ) );
			debits.emplace_back( i, take );
			auto copy = item; copy.amount = static_cast<int16>( take ); refunds.push_back( copy );
			left -= take;
		}
		if( left ) { fail( "inventory changed" ); return; }
	}
	if( attachments ) {
		std::vector<std::pair<int32, int32>> appearance_changes;
		for( const auto& entry : entries )
			if( entry->look == LOOK_HAIR || entry->look == LOOK_HAIR_COLOR || entry->look == LOOK_CLOTHES_COLOR || entry->look == LOOK_BODY2 )
				appearance_changes.emplace_back(entry->look, entry->value);
		if( reset_color ) appearance_changes.emplace_back(LOOK_HAIR_COLOR, 0);
		if( !chrif_stylist_purchase(*sd, mail, payment.zeny, debits, appearance_changes) ) fail("durable purchase unavailable");
		return; // Only char-server's durable result may confirm this purchase.
	}
	if( payment.zeny && pc_payzeny( sd, payment.zeny, LOG_TYPE_OTHER ) != 0 ) { fail( "zeny debit" ); return; }
	size_t consumed = 0;
	auto refund = [&](){
		for( size_t i = 0; i < consumed; ++i ){
			if( pc_additem( sd, &refunds[i], refunds[i].amount, LOG_TYPE_OTHER ) != ADDITEM_SUCCESS )
				ShowError( "Stylist refund invariant failed char=%d item=%u amount=%d\n", sd->status.char_id, refunds[i].nameid, refunds[i].amount );
		}
		if( payment.zeny ) pc_getzeny( sd, payment.zeny, LOG_TYPE_OTHER );
	};
	for( const auto& debit : debits ){
		if( pc_delitem( sd, debit.first, debit.second, 0, 0, LOG_TYPE_OTHER ) != 0 ){
			refund(); fail( "item debit" ); return;
		}
		++consumed;
	}
	for( const auto& entry : entries ){
		if( entry->look == LOOK_HAIR || entry->look == LOOK_HAIR_COLOR || entry->look == LOOK_CLOTHES_COLOR || entry->look == LOOK_BODY2 )
			pc_changelook( sd, entry->look, entry->value );
	}
	if( reset_color ) pc_changelook( sd, LOOK_HAIR_COLOR, 0 );
	chrif_save( sd, CSAVE_INVENTORY );
	clif_stylist_response( sd, false );
}
#endif
// End Stylist: purchase

// Stylist: delivery
struct s_stylist_pending {
	s_stylist_request request{};
	uint32 zeny = 0;
	std::vector<std::pair<int32, int32>> debits, looks;
	std::vector<uint32> item_ids;
	int32 save_flags = CSAVE_INVENTORY;
	t_tick last_send = 0;
};
static std::unordered_map<uint32, std::weak_ptr<s_stylist_pending>> stylist_pending;

uint32 chrif_stylist_reserved_zeny(const map_session_data& sd) {
	return sd.stylist_purchase == nullptr ? 0 : sd.stylist_purchase->zeny;
}
int32 chrif_stylist_reserved_item(const map_session_data& sd, int32 index) {
	if( sd.stylist_purchase != nullptr ) for( const auto& debit : sd.stylist_purchase->debits )
		if( debit.first == index ) return debit.second;
	return 0;
}
static void chrif_stylist_send(map_session_data& sd) {
	if( !chrif_isconnected() || sd.stylist_purchase == nullptr ) return;
	auto& pending = *sd.stylist_purchase;
	if( pending.last_send != 0 && DIFF_TICK(gettick(), pending.last_send) < 5000 ) return;
	pending.last_send = gettick();
	// Includes disconnected players retained in auth_db until their final save.
	chrif_char_online(&sd);
	WFIFOHEAD(char_fd, sizeof(pending.request));
	memcpy(WFIFOP(char_fd, 0), &pending.request, sizeof(pending.request));
	WFIFOSET(char_fd, sizeof(pending.request));
}
void chrif_stylist_retry_all() {
	for( auto it = stylist_pending.begin(); it != stylist_pending.end(); ) {
		auto pending = it->second.lock();
		if( pending == nullptr ) { it = stylist_pending.erase(it); continue; }
		auto sd = map_charid2sd(pending->request.char_id);
		if( sd == nullptr ) {
			auto node = chrif_search(pending->request.account_id);
			if( node != nullptr && node->char_id == pending->request.char_id ) sd = node->sd;
		}
		if( sd != nullptr && sd->stylist_purchase == pending ) chrif_stylist_send(*sd);
		++it;
	}
}
bool chrif_stylist_purchase(map_session_data& sd, const mail_message& mail, uint32 zeny,
	const std::vector<std::pair<int32, int32>>& debits, const std::vector<std::pair<int32, int32>>& looks) {
	if( !chrif_isconnected() || sd.stylist_purchase != nullptr || zeny > static_cast<uint32>(sd.status.zeny) ) return false;
	auto pending = std::make_shared<s_stylist_pending>();
	auto& request = pending->request;
	request.header = STYLIST_PURCHASE_REQUEST; request.length = sizeof(request);
	std::random_device entropy;
	for( size_t i = 0; i < 4; ++i ) snprintf(request.operation + i * 8, 9, "%08x", static_cast<uint32>(entropy()));
	request.account_id = sd.status.account_id; request.char_id = sd.status.char_id; request.job = sd.status.class_;
	request.zeny = sd.status.zeny - zeny;
	request.hair = sd.status.hair; request.hair_color = sd.status.hair_color;
	request.clothes_color = sd.status.clothes_color; request.body = sd.status.body;
	std::copy(std::begin(sd.inventory.u.items_inventory), std::end(sd.inventory.u.items_inventory), request.inventory);
	std::copy_n(mail.item, 3, request.accessories);
	for( const auto& debit : debits ) {
		if( debit.first < 0 || debit.first >= MAX_INVENTORY || debit.second <= 0 ) return false;
		auto& item = request.inventory[debit.first];
		if( item.nameid == 0 || item.amount < debit.second || item.equip || item.equipSwitch || item.expire_time ) return false;
		pending->item_ids.push_back(item.nameid);
		item.amount = static_cast<int16>(item.amount - debit.second);
		if( item.amount == 0 ) item = {};
	}
	for( const auto& look : looks ) {
		if( look.second < 0 || look.second > UINT16_MAX ) return false;
		const auto value = static_cast<uint16>(look.second);
		switch( look.first ) {
			case LOOK_HAIR: request.hair = value; break;
			case LOOK_HAIR_COLOR: request.hair_color = value; break;
			case LOOK_CLOTHES_COLOR: request.clothes_color = value; break;
			case LOOK_BODY2: request.body = value; break;
			default: return false;
		}
	}
	if( !battle_config.save_clothcolor ) request.clothes_color = 0;
	if( !battle_config.save_body_style ) request.body = request.job;
	pending->zeny = zeny; pending->debits = debits; pending->looks = looks;
	// Save precedes this transaction on the same ordered inter-server stream.
	chrif_save(&sd, CSAVE_INVENTORY);
	sd.stylist_purchase = pending;
	stylist_pending[sd.status.char_id] = pending;
	chrif_stylist_send(sd);
	return true;
}
void chrif_stylist_reply(int32 fd) {
	s_stylist_reply reply{}; memcpy(&reply, RFIFOP(fd, 0), sizeof(reply));
	auto sd = map_charid2sd(reply.char_id);
	if( sd == nullptr ) {
		auto node = chrif_search(reply.account_id);
		if( node != nullptr && node->char_id == reply.char_id ) sd = node->sd;
	}
	if( sd == nullptr || sd->status.account_id != reply.account_id || sd->stylist_purchase == nullptr ) return;
	auto pending = sd->stylist_purchase;
	if( memcmp(reply.operation, pending->request.operation, sizeof(reply.operation)) != 0 ) return;
	if( reply.result != StylistPurchaseResult::Committed && reply.result != StylistPurchaseResult::Rejected ) return;
	if( reply.result == StylistPurchaseResult::Committed ) {
		bool intact = static_cast<uint32>(sd->status.zeny) >= pending->zeny;
		for( size_t i = 0; i < pending->debits.size(); ++i ) {
			const auto& debit = pending->debits[i];
			const auto& item = sd->inventory.u.items_inventory[debit.first];
			intact = intact && item.nameid == pending->item_ids[i] && item.amount >= debit.second && sd->inventory_data[debit.first] != nullptr;
		}
		if( !intact ) {
			// Direct custom writes bypassed the resource reservation API. Never save
			// that corrupt in-memory state over the already committed SQL balance.
			ShowError("Stylist reservation invariant failed char=%u operation=%s; requires reconciliation.\n", reply.char_id, reply.operation);
			return;
		}
	}
	sd->stylist_purchase.reset();
	stylist_pending.erase(reply.char_id);
	const bool committed = reply.result == StylistPurchaseResult::Committed;
	if( committed ) {
		if( pending->zeny ) pc_payzeny(sd, pending->zeny, LOG_TYPE_OTHER);
		for( const auto& debit : pending->debits ) pc_delitem(sd, debit.first, debit.second, 0, 0, LOG_TYPE_OTHER);
		for( const auto& look : pending->looks ) pc_changelook(sd, look.first, look.second);
	}
	if( sd->fd > 0 ) clif_stylist_response(sd, !committed);
	pc_stylist_revalidate(*sd); // Configuration/catalogue may have changed while waiting.
	// Also persists unrelated changes/rewards and a deferred final logout.
	chrif_save(sd, pending->save_flags);
}

void chrif_stylist_defer_save(map_session_data& sd, int32 flags) {
	sd.stylist_purchase->save_flags |= flags;
	chrif_stylist_send(sd);
}
// End Stylist: delivery
