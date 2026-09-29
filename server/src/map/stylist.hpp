// Copyright (c) rAthena Dev Teams - Licensed under GNU GPL
#ifndef STYLIST_HPP
#define STYLIST_HPP

#include <common/mmo.hpp>
#include <algorithm>
#include <iterator>

// Stylist: inter-server protocol
constexpr uint16 STYLIST_PURCHASE_REQUEST = 0x2b30;
constexpr uint16 STYLIST_PURCHASE_REPLY = 0x2b31;
enum class StylistPurchaseResult : uint8 { Committed = 1, Rejected = 2, Retry = 3 };

// Private map/char protocol, like the existing inventory protocol. Both servers
// must be built with the same item layout and MAX_INVENTORY configuration.
#pragma pack(push, 1)
struct s_stylist_request {
	uint16 header;
	uint16 length;
	char operation[33]; // Random 128-bit identifier, hex encoded.
	uint32 account_id;
	uint32 char_id;
	uint16 job;
	uint32 zeny;
	uint16 hair, hair_color, clothes_color, body;
	struct item inventory[MAX_INVENTORY];
	struct item accessories[3];
};
struct s_stylist_reply {
	uint16 header;
	char operation[33];
	uint32 account_id;
	uint32 char_id;
	StylistPurchaseResult result;
	uint32 mail_id;
};
#pragma pack(pop)
static_assert(sizeof(s_stylist_request) <= UINT16_MAX, "Stylist purchase exceeds inter-server packet size");
// End Stylist: inter-server protocol

// Stylist: appearance
namespace stylist {
#define STYLIST_NONE UINT16_MAX
struct Lineage { uint8 sex; uint16 second, trans, third, third_t, alternate, fourth; };
inline constexpr Lineage lineages[] = {
#define STYLIST_LINEAGE(gender, ...) { static_cast<uint8>(gender), __VA_ARGS__ },
// Shared by the server policy and tools/stylist/generate_catalogue.py.
// STYLIST_LINEAGE(sex, second, trans, third, third_t, alternate, fourth)
// Every listed job of a branch may wear every outfit of that branch: second,
// trans, third, alternate and fourth.
// Third-job outfits offered to other tiers use third_t (4060-4065, 4073-4079).
// First, *_HIGH, Baby and Novice jobs are never listed. STYLIST_NONE marks a missing tier.
STYLIST_LINEAGE(SEX_BOTH, JOB_KNIGHT, JOB_LORD_KNIGHT, JOB_RUNE_KNIGHT, JOB_RUNE_KNIGHT_T, JOB_RUNE_KNIGHT_2ND, JOB_DRAGON_KNIGHT)
STYLIST_LINEAGE(SEX_BOTH, JOB_CRUSADER, JOB_PALADIN, JOB_ROYAL_GUARD, JOB_ROYAL_GUARD_T, JOB_ROYAL_GUARD_2ND, JOB_IMPERIAL_GUARD)
STYLIST_LINEAGE(SEX_BOTH, JOB_WIZARD, JOB_HIGH_WIZARD, JOB_WARLOCK, JOB_WARLOCK_T, JOB_WARLOCK_2ND, JOB_ARCH_MAGE)
STYLIST_LINEAGE(SEX_BOTH, JOB_SAGE, JOB_PROFESSOR, JOB_SORCERER, JOB_SORCERER_T, JOB_SORCERER_2ND, JOB_ELEMENTAL_MASTER)
STYLIST_LINEAGE(SEX_BOTH, JOB_HUNTER, JOB_SNIPER, JOB_RANGER, JOB_RANGER_T, JOB_RANGER_2ND, JOB_WINDHAWK)
STYLIST_LINEAGE(SEX_MALE, JOB_BARD, JOB_CLOWN, JOB_MINSTREL, JOB_MINSTREL_T, JOB_MINSTREL_2ND, JOB_TROUBADOUR)
STYLIST_LINEAGE(SEX_FEMALE, JOB_DANCER, JOB_GYPSY, JOB_WANDERER, JOB_WANDERER_T, JOB_WANDERER_2ND, JOB_TROUVERE)
STYLIST_LINEAGE(SEX_BOTH, JOB_PRIEST, JOB_HIGH_PRIEST, JOB_ARCH_BISHOP, JOB_ARCH_BISHOP_T, JOB_ARCHBISHOP_2ND, JOB_CARDINAL)
STYLIST_LINEAGE(SEX_BOTH, JOB_MONK, JOB_CHAMPION, JOB_SURA, JOB_SURA_T, JOB_SURA_2ND, JOB_INQUISITOR)
STYLIST_LINEAGE(SEX_BOTH, JOB_BLACKSMITH, JOB_WHITESMITH, JOB_MECHANIC, JOB_MECHANIC_T, JOB_MECHANIC_2ND, JOB_MEISTER)
STYLIST_LINEAGE(SEX_BOTH, JOB_ALCHEMIST, JOB_CREATOR, JOB_GENETIC, JOB_GENETIC_T, JOB_GENETIC_2ND, JOB_BIOLO)
STYLIST_LINEAGE(SEX_BOTH, JOB_ASSASSIN, JOB_ASSASSIN_CROSS, JOB_GUILLOTINE_CROSS, JOB_GUILLOTINE_CROSS_T, JOB_GUILLOTINE_CROSS_2ND, JOB_SHADOW_CROSS)
STYLIST_LINEAGE(SEX_BOTH, JOB_ROGUE, JOB_STALKER, JOB_SHADOW_CHASER, JOB_SHADOW_CHASER_T, JOB_SHADOW_CHASER_2ND, JOB_ABYSS_CHASER)
STYLIST_LINEAGE(SEX_BOTH, JOB_SUPER_NOVICE, STYLIST_NONE, JOB_SUPER_NOVICE_E, STYLIST_NONE, STYLIST_NONE, JOB_HYPER_NOVICE)
STYLIST_LINEAGE(SEX_BOTH, JOB_STAR_GLADIATOR, STYLIST_NONE, JOB_STAR_EMPEROR, STYLIST_NONE, STYLIST_NONE, JOB_SKY_EMPEROR)
STYLIST_LINEAGE(SEX_BOTH, JOB_SOUL_LINKER, STYLIST_NONE, JOB_SOUL_REAPER, STYLIST_NONE, STYLIST_NONE, JOB_SOUL_ASCETIC)
STYLIST_LINEAGE(SEX_MALE, JOB_NINJA, STYLIST_NONE, JOB_KAGEROU, STYLIST_NONE, STYLIST_NONE, JOB_SHINKIRO)
STYLIST_LINEAGE(SEX_FEMALE, JOB_NINJA, STYLIST_NONE, JOB_OBORO, STYLIST_NONE, STYLIST_NONE, JOB_SHIRANUI)
STYLIST_LINEAGE(SEX_BOTH, JOB_GUNSLINGER, STYLIST_NONE, JOB_REBELLION, STYLIST_NONE, STYLIST_NONE, JOB_NIGHT_WATCH)
STYLIST_LINEAGE(SEX_BOTH, JOB_SUMMONER, STYLIST_NONE, STYLIST_NONE, STYLIST_NONE, STYLIST_NONE, JOB_SPIRIT_HANDLER)
#undef STYLIST_LINEAGE
};

// Tier inside one line: 2 second, 3 transcendent, 4 third, 5 fourth; 0 when absent.
inline uint8 tier_in(const Lineage& line, uint16 job) {
	if( job == STYLIST_NONE ) return 0;
	if( job == line.second ) return 2;
	if( job == line.trans ) return 3;
	if( job == line.third || job == line.third_t ) return 4;
	if( job == line.fourth ) return 5;
	return 0;
}

inline uint8 costume_tier(uint16 job) {
	for( const auto& line : lineages )
		if( const uint8 tier = tier_in(line, job) ) return tier;
	return 0;
}

// Every job of a branch (second, transcendent, third, third_t, fourth) may
// wear every outfit of that branch: second, transcendent, third, alternate and
// fourth. Third jobs wear their own third outfit; other tiers get third_t,
// which looks the same. Mirrors generate_catalogue.py.
inline bool lineage_allows(uint16 job, uint32 body, uint8 sex = SEX_BOTH) {
	if( body > UINT16_MAX ) return false;
	for( const auto& line : lineages ){
		if( sex != SEX_BOTH && line.sex != SEX_BOTH && line.sex != sex ) continue;
		const uint8 tier = tier_in(line, job);
		if( tier == 0 ) continue;
		const uint16 third = line.third_t != STYLIST_NONE ? line.third_t : line.third;
		const uint16 targets[] = {
			job,
			line.second,
			line.trans,
			tier != 4 ? third : STYLIST_NONE,
			line.alternate,
			line.fourth,
		};
		for( const uint16 target : targets )
			if( target != STYLIST_NONE && target == body ) return true;
	}
	return false;
}

inline bool is_baby(uint16 job) {
	constexpr uint16 babies[] = {
		JOB_BABY, JOB_BABY_ACOLYTE, JOB_BABY_ALCHEMIST, JOB_BABY_ARCH_BISHOP, JOB_BABY_ARCHER, JOB_BABY_ASSASSIN,
		JOB_BABY_BARD, JOB_BABY_BLACKSMITH, JOB_BABY_CRUSADER, JOB_BABY_CRUSADER2, JOB_BABY_DANCER, JOB_BABY_GENETIC,
		JOB_BABY_GUILLOTINE_CROSS, JOB_BABY_GUNSLINGER, JOB_BABY_HUNTER, JOB_BABY_KAGEROU, JOB_BABY_KNIGHT,
		JOB_BABY_KNIGHT2, JOB_BABY_MAGE, JOB_BABY_MECHANIC, JOB_BABY_MECHANIC2, JOB_BABY_MERCHANT, JOB_BABY_MINSTREL,
		JOB_BABY_MONK, JOB_BABY_NINJA, JOB_BABY_OBORO, JOB_BABY_PRIEST, JOB_BABY_RANGER, JOB_BABY_RANGER2,
		JOB_BABY_REBELLION, JOB_BABY_ROGUE, JOB_BABY_ROYAL_GUARD, JOB_BABY_ROYAL_GUARD2, JOB_BABY_RUNE_KNIGHT,
		JOB_BABY_RUNE_KNIGHT2, JOB_BABY_SAGE, JOB_BABY_SHADOW_CHASER, JOB_BABY_SORCERER, JOB_BABY_SOUL_LINKER,
		JOB_BABY_SOUL_REAPER, JOB_BABY_STAR_EMPEROR, JOB_BABY_STAR_EMPEROR2, JOB_BABY_STAR_GLADIATOR,
		JOB_BABY_STAR_GLADIATOR2, JOB_BABY_SUMMONER, JOB_BABY_SURA, JOB_BABY_SWORDMAN, JOB_BABY_TAEKWON,
		JOB_BABY_THIEF, JOB_BABY_WANDERER, JOB_BABY_WARLOCK, JOB_BABY_WIZARD, JOB_SUPER_BABY, JOB_SUPER_BABY_E
	};
	return std::find(std::begin(babies), std::end(babies), job) != std::end(babies);
}

// stylist_costume_jobs bits: 1 every job but Novice, 2 second, 4 transcendent,
// 8 third, 16 fourth. Novices and babies never change outfits.
inline bool costume_access(uint16 job, int32 mask) {
	if( job == JOB_NOVICE || job == JOB_NOVICE_HIGH || is_baby(job) ) return false;
	if( mask & 1 ) return true;
	switch( costume_tier(job) ){
		case 2: return (mask & 2) != 0;
		case 3: return (mask & 4) != 0;
		case 4: return (mask & 8) != 0;
		case 5: return (mask & 16) != 0;
	}
	return false;
}

inline uint16 body_for_sex(uint16 body, uint8 sex) {
	constexpr uint16 pairs[][2] = {
		{JOB_DANCER, JOB_BARD}, {JOB_GYPSY, JOB_CLOWN}, {JOB_BABY_DANCER, JOB_BABY_BARD},
		{JOB_WANDERER, JOB_MINSTREL}, {JOB_WANDERER_T, JOB_MINSTREL_T},
		{JOB_BABY_WANDERER, JOB_BABY_MINSTREL}, {JOB_TROUVERE, JOB_TROUBADOUR},
		{JOB_WANDERER_2ND, JOB_MINSTREL_2ND}, {JOB_OBORO, JOB_KAGEROU},
		{JOB_BABY_OBORO, JOB_BABY_KAGEROU}, {JOB_SHIRANUI, JOB_SHINKIRO}
	};
	if( sex > SEX_MALE ) return body;
	for( const auto& pair : pairs ) if( body == pair[0] || body == pair[1] ) return pair[sex];
	return body;
}

// Lifecycle policy is shared by login, job/sex changes, reloads and tests.
template<class Allowed>
uint16 reconcile_body(uint16 job, uint32 body, uint8 sex, Allowed allowed) {
	if( body > UINT16_MAX ) return job;
	const uint16 candidate = body_for_sex(static_cast<uint16>(body), sex);
	return allowed(job, candidate, sex) ? candidate : job;
}

inline uint16 visible_body(uint16 job, uint16 body, bool temporary_appearance) {
	return temporary_appearance ? job : body;
}

template<class Allowed>
uint16 body_after_job_change(uint16 old_job, uint16 new_job, uint16 body, uint8 sex, Allowed allowed) {
	return body == old_job ? new_job : reconcile_body(new_job, body, sex, allowed);
}
}
// End Stylist: appearance

// Stylist: payment protocol
#include <cstdint>
#include <cstddef>
#include <vector>
#include <map>
#include <set>
#include <limits>

namespace stylist {
struct Selection { int32_t action; int16_t index; };
inline uint16_t u16(const uint8_t* p) { return uint16_t(p[0]) | (uint16_t(p[1]) << 8); }
inline uint32_t u32(const uint8_t* p) { return uint32_t(u16(p)) | (uint32_t(u16(p + 2)) << 16); }
// Zero-valued slots are emitted by this client for unchanged categories. Multiple
// {0,0} placeholders are valid; duplicate *selected* categories are not.
inline bool decode(const uint8_t* p, size_t size, bool doram, std::vector<Selection>& out) {
	out.clear();
	if (size < 6 || u16(p) != 0x0bf7 || u16(p + 2) != size) return false;
	const size_t count = u16(p + 4);
	if (count == 0 || count > 16 || size != 6 + 8 * count) return false;
	std::set<int32_t> seen;
	std::vector<Selection> result;
	for (size_t i = 0; i < count; ++i) {
		const uint32_t action = u32(p + 6 + i * 8), raw = u32(p + 10 + i * 8);
		if (action > 9 || action == 7) return false;
		if (raw == 0) continue;
		if ((action == 6 || action == 8) && !doram) return false;
		if ((action == 1 || action == 2) && doram) return false;
		const int32_t canonical = action == 6 ? 1 : action == 8 ? 2 : action;
		if (!seen.insert(canonical).second) return false;
		// -1 is a documented catalogue sentinel, never truncate an arbitrary dword.
		if (raw != UINT32_MAX && raw > INT16_MAX) return false;
		result.push_back({canonical, raw == UINT32_MAX ? int16_t(-1) : int16_t(raw)});
	}
	if (result.empty()) return false;
	out.swap(result);
	return true;
}
struct Cost { uint32_t zeny = 0, item = 0, box = 0; };
struct Payment { uint32_t zeny = 0; std::map<uint32_t, uint32_t> items; };
inline bool allocate(const std::vector<Cost>& costs, size_t pos,
	std::map<uint32_t, uint32_t>& stock, std::map<uint32_t, uint32_t>& used) {
	if (pos == costs.size()) return true;
	const auto& c = costs[pos];
	if (!c.item && !c.box) return allocate(costs, pos + 1, stock, used);
	for (const uint32_t id : {c.item, c.box}) {
		if (!id || stock[id] == 0) continue;
		--stock[id]; ++used[id];
		if (allocate(costs, pos + 1, stock, used)) return true;
		++stock[id]; if (--used[id] == 0) used.erase(id);
	}
	return false;
}
inline bool plan_payment(const std::vector<Cost>& costs, uint32_t wallet,
	const std::map<uint32_t, uint32_t>& inventory, Payment& out) {
	out = {};
	if (costs.empty() || costs.size() > 7) return false;
	uint64_t total = 0;
	for (const auto& cost : costs) total += cost.zeny;
	if (total > wallet || total > INT32_MAX) return false;
	auto stock = inventory;
	Payment plan;
	if (!allocate(costs, 0, stock, plan.items)) return false;
	plan.zeny = static_cast<uint32_t>(total);
	out = plan;
	return true;
}
}
// End Stylist: payment protocol

// Map-server integration. The shared packet structures above also serve char-server.
class map_session_data;
void clif_stylist_buy_modern(int32 fd, map_session_data* sd);
void chrif_stylist_retry_all();
void chrif_stylist_reply(int32 fd);
void chrif_stylist_defer_save(map_session_data& sd, int32 flags);

#endif // STYLIST_HPP
