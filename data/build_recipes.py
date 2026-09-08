"""Builds data/recipes.json from a compact declarative table.

Every ingredient id must exist in food_catalog.csv - the script fails loudly
otherwise, so the recipe index can never drift away from the catalog.
"""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def ing(spec):
    """'spinach:400' -> required, 'cream:50?' -> optional."""
    out = []
    for part in spec.split():
        optional = part.endswith("?")
        part = part.rstrip("?")
        fid, grams = part.split(":")
        out.append({"id": fid, "grams": float(grams), "optional": optional})
    return out


# title | cuisine | meal | diet | minutes | servings | ingredients | steps | rescue_note
R = [
 ("palak_paneer", "Palak Paneer", "North Indian", "dinner", "vegetarian", 30, 3,
  "spinach:400 paneer:200 onion:100 tomato:120 ginger:10 garlic:10 green_chilli:8 cream:40? garam_masala:4 cooking_oil:20",
  ["Blanch spinach 2 minutes, shock in cold water, then blend to a coarse puree.",
   "Fry onion, ginger, garlic and chilli in oil until golden; add tomato and cook until soft.",
   "Stir in the puree and garam masala, simmer 5 minutes.",
   "Add cubed paneer and cream, warm through and serve."],
  "The single best rescue for spinach that has started to wilt - blanching revives limp leaves."),

 ("methi_thepla", "Methi Thepla", "Gujarati", "breakfast", "vegetarian", 35, 4,
  "methi:200 atta:300 besan:60 curd:80 turmeric:3 chilli_powder:4 cooking_oil:40",
  ["Chop fenugreek leaves finely and mix with flours, curd, spices and a little water.",
   "Knead a soft dough and rest 10 minutes.",
   "Roll thin discs and cook on a hot tawa with oil until both sides are speckled."],
  "Uses a full bunch of methi at once and the theplas keep for two days."),

 ("tomato_soup", "Fresh Tomato Soup", "Continental", "lunch", "vegetarian", 25, 3,
  "tomato:600 onion:80 garlic:10 butter:20 cream:30? sugar:5 salt:4",
  ["Sweat onion and garlic in butter without browning.",
   "Add roughly chopped tomatoes, a cup of water, sugar and salt; simmer 15 minutes.",
   "Blend smooth, strain if you like, and finish with cream."],
  "Overripe or slightly soft tomatoes actually make a sweeter soup than firm ones."),

 ("veg_pulao", "Vegetable Pulao", "North Indian", "dinner", "vegan", 35, 4,
  "rice:300 carrot:100 peas_fresh:100 beans_french:80 onion:100 garam_masala:5 ghee:25",
  ["Rinse and soak rice 20 minutes.",
   "Fry onion in ghee until golden, add vegetables and garam masala, saute 3 minutes.",
   "Add rice and 1.5x water, cook covered on low until done, then rest 5 minutes before fluffing."],
  "A flexible base - swap in whatever vegetables are closest to turning."),

 ("fried_rice_leftover", "Leftover Fried Rice", "Indo-Chinese", "lunch", "vegan", 15, 2,
  "cooked_rice:400 capsicum:80 carrot:80 spring_onion:50 cabbage:100 garlic:12 cooking_oil:20",
  ["Heat oil very hot, add garlic and the hardest vegetables first.",
   "Toss in cabbage and capsicum for 2 minutes on high heat.",
   "Add cold cooked rice, season, and stir-fry until every grain is coated. Finish with spring onion."],
  "Day-old rice fries better than fresh - this is the highest-value use of leftover rice."),

 ("dal_tadka", "Dal Tadka", "North Indian", "dinner", "vegetarian", 40, 4,
  "toor_dal:200 onion:80 tomato:100 garlic:12 ginger:10 green_chilli:8 ghee:25 turmeric:3 coriander:15",
  ["Pressure cook dal with turmeric and salt until soft.",
   "Make a tempering of ghee, garlic, ginger, chilli, onion and tomato.",
   "Pour the tempering over the dal, simmer 5 minutes and finish with coriander."],
  "Cook a big batch - dal freezes well and rescues you on a busy night."),

 ("mixed_veg_sabzi", "Mixed Vegetable Sabzi", "North Indian", "dinner", "vegan", 30, 4,
  "potato:200 cauliflower:250 peas_fresh:100 tomato:120 onion:100 turmeric:3 garam_masala:4 cooking_oil:25",
  ["Fry onion until soft, add tomato and spices and cook to a paste.",
   "Add potato and cauliflower with a splash of water, cover and cook 12 minutes.",
   "Stir in peas, cook 3 more minutes and serve."],
  "The catch-all dish for a fridge with small amounts of many vegetables."),

 ("bhindi_masala", "Bhindi Masala", "North Indian", "dinner", "vegan", 25, 3,
  "okra:300 onion:120 tomato:100 besan:20 chilli_powder:4 cooking_oil:30",
  ["Wipe okra dry and slice; never wash after cutting or it turns slimy.",
   "Fry okra on high heat until edges crisp, then remove.",
   "Fry onion and tomato with spices, sprinkle besan, return okra and toss."],
  "Okra deteriorates fast - cook it within two days of buying."),

 ("baingan_bharta", "Baingan Bharta", "North Indian", "dinner", "vegan", 40, 3,
  "brinjal:400 onion:120 tomato:150 green_chilli:8 garlic:12 mustard_oil:25 coriander:15",
  ["Char the brinjal directly over a flame until the skin blisters and the flesh collapses.",
   "Peel and mash roughly.",
   "Fry garlic, onion, chilli and tomato in mustard oil, add the mash and cook 8 minutes.",
   "Finish with plenty of coriander."],
  "Works even with a brinjal that has gone slightly soft."),

 ("aloo_gobi", "Aloo Gobi", "North Indian", "dinner", "vegan", 30, 4,
  "potato:250 cauliflower:300 onion:80 tomato:100 turmeric:3 coriander:15 cooking_oil:25",
  ["Cut potato and cauliflower into even florets and cubes.",
   "Fry with turmeric and salt, covered, stirring occasionally for 15 minutes.",
   "Add tomato near the end so it does not make things soggy; finish with coriander."],
  "Cauliflower keeps a while but yellowing florets should be used immediately."),

 ("cabbage_poriyal", "Cabbage Poriyal", "South Indian", "lunch", "vegan", 20, 4,
  "cabbage:400 coconut:60 curry_leaves:5 green_chilli:8 cooking_oil:15",
  ["Shred cabbage finely.",
   "Temper curry leaves and chilli in oil, add cabbage and a pinch of salt.",
   "Cook uncovered 8 minutes so it stays crunchy, then stir through grated coconut."],
  "Half a cabbage sitting in the fridge becomes a full side dish in 20 minutes."),

 ("lauki_chana_dal", "Lauki Chana Dal", "North Indian", "dinner", "vegetarian", 40, 4,
  "bottle_gourd:400 chana_dal:150 tomato:100 turmeric:3 ghee:20 green_chilli:6",
  ["Soak chana dal 30 minutes.",
   "Pressure cook dal with diced lauki, tomato, turmeric and salt.",
   "Finish with a ghee and chilli tempering."],
  "Bottle gourd is bulky and often half-used - this dish takes a whole one."),

 ("veg_upma", "Vegetable Upma", "South Indian", "breakfast", "vegetarian", 25, 3,
  "suji:200 onion:80 carrot:80 peas_fresh:60 curry_leaves:5 green_chilli:8 cooking_oil:25",
  ["Dry roast semolina until it smells nutty, then set aside.",
   "Temper curry leaves and chilli, add onion, carrot and peas and saute.",
   "Add 3x water, bring to a boil, then rain in the semolina while stirring.",
   "Cover and steam 3 minutes."],
  "Absorbs small leftover quantities of almost any vegetable."),

 ("poha", "Kanda Poha", "Maharashtrian", "breakfast", "vegan", 20, 3,
  "poha:200 onion:120 potato:100 green_chilli:8 curry_leaves:5 groundnut:40 lemon:20",
  ["Rinse poha in a colander until just soft, never soaking.",
   "Fry groundnuts, then temper curry leaves, chilli, onion and potato.",
   "Fold in poha with turmeric and salt, steam 3 minutes, finish with lemon."],
  "A ten-rupee breakfast that clears leftover onions and potatoes."),

 ("besan_chilla", "Besan Chilla", "North Indian", "breakfast", "vegan", 20, 2,
  "besan:150 onion:80 tomato:80 coriander:15 green_chilli:6 turmeric:3 cooking_oil:20",
  ["Whisk besan with water to a pouring batter; rest 10 minutes.",
   "Stir in chopped onion, tomato, coriander and chilli.",
   "Cook like a pancake on a hot tawa with a little oil."],
  "The fastest way to use up small bits of vegetables and a lot of coriander."),

 ("masala_omelette", "Masala Omelette", "Indian", "breakfast", "egg", 10, 2,
  "eggs:150 onion:60 tomato:60 green_chilli:6 coriander:10 cooking_oil:12",
  ["Beat eggs with salt until slightly frothy.",
   "Mix in finely chopped onion, tomato, chilli and coriander.",
   "Cook on medium heat, fold once the top is just set."],
  "Two minutes, and it uses eggs that are nearing their date."),

 ("egg_bhurji", "Egg Bhurji", "Indian", "dinner", "egg", 15, 3,
  "eggs:200 onion:100 tomato:100 capsicum:80 green_chilli:8 butter:20",
  ["Fry onion, capsicum and chilli in butter until soft.",
   "Add tomato and cook until it breaks down.",
   "Pour in beaten eggs and scramble on low heat so they stay creamy."],
  "Great for a half capsicum and a lone tomato."),

 ("paneer_bhurji", "Paneer Bhurji", "North Indian", "dinner", "vegetarian", 20, 3,
  "paneer:250 onion:100 tomato:120 capsicum:80 green_chilli:8 coriander:15 cooking_oil:20",
  ["Crumble the paneer coarsely.",
   "Fry onion, capsicum, chilli, then tomato until pulpy.",
   "Add paneer, toss 3 minutes only - overcooking makes it rubbery."],
  "Paneer has a short fridge life; crumbling hides any slight firming."),

 ("chicken_curry", "Home Chicken Curry", "North Indian", "dinner", "non-veg", 45, 4,
  "chicken:600 onion:200 tomato:200 curd:100 ginger:15 garlic:15 garam_masala:6 mustard_oil:30",
  ["Marinate chicken in curd, ginger, garlic and salt for 20 minutes.",
   "Brown onions deeply in mustard oil, add tomato and cook down.",
   "Add chicken and marinade, cook covered 25 minutes, finish with garam masala."],
  "Raw chicken must be used within two days - cook or freeze it immediately."),

 ("fish_fry", "Tawa Fish Fry", "Coastal", "dinner", "non-veg", 20, 3,
  "fish:500 lemon:25 turmeric:4 chilli_powder:5 suji:50 mustard_oil:40",
  ["Marinate fish in lemon, turmeric, chilli and salt for 15 minutes.",
   "Dust with semolina for crunch.",
   "Shallow fry in mustard oil, 4 minutes a side, without moving it around."],
  "Fish is the most perishable item in any fridge - cook the day you buy."),

 ("prawn_masala", "Prawn Masala", "Coastal", "dinner", "non-veg", 25, 3,
  "prawns:400 onion:150 tomato:150 garlic:15 coconut:60 chilli_powder:5 cooking_oil:25",
  ["Fry garlic and onion, add tomato and spices and cook to a thick masala.",
   "Add prawns and cook only 5 minutes until they curl and turn opaque.",
   "Stir in grated coconut and take off the heat."],
  "Prawns carry a very high carbon footprint, so wasting them is especially costly."),

 ("mutton_curry", "Slow Mutton Curry", "North Indian", "dinner", "non-veg", 90, 4,
  "mutton:700 onion:250 curd:120 ginger:20 garlic:20 garam_masala:8 mustard_oil:40",
  ["Marinate mutton in curd, ginger and garlic for an hour.",
   "Brown onions slowly in mustard oil until deep brown.",
   "Add mutton, sear, then pressure cook 25 minutes with a cup of water.",
   "Reduce the gravy and finish with garam masala."],
  "Mutton has the highest footprint in the catalog after beef - portion carefully."),

 ("veg_sandwich", "Grilled Veg Sandwich", "Continental", "snack", "vegetarian", 12, 2,
  "bread:160 cucumber:80 tomato:80 capsicum:60 butter:20 cheese:40 mayonnaise:20?",
  ["Butter the bread on the outside for a crisp grill.",
   "Layer thin cucumber, tomato and capsicum with cheese and a little seasoning.",
   "Grill or pan-press until golden."],
  "Bread staling? Grilling completely hides it."),

 ("french_toast", "French Toast", "Continental", "breakfast", "egg", 12, 2,
  "bread:160 eggs:100 milk:100 sugar:20 butter:20",
  ["Whisk eggs, milk and sugar.",
   "Soak each slice 10 seconds a side.",
   "Fry in butter until deep golden."],
  "The classic rescue for bread that is one day past its best."),

 ("bread_upma", "Bread Upma", "Indian", "breakfast", "vegetarian", 15, 2,
  "bread:200 onion:80 tomato:80 capsicum:60 curry_leaves:5 cooking_oil:20",
  ["Cube the bread and toast lightly in a dry pan.",
   "Temper curry leaves, fry onion, capsicum and tomato with salt and turmeric.",
   "Fold in the bread cubes so they soak up the masala without going mushy."],
  "Designed for stale bread - fresh bread actually works worse here."),

 ("banana_pancake", "Banana Pancakes", "Continental", "breakfast", "egg", 20, 3,
  "banana:300 atta:150 milk:150 eggs:100 honey:30 butter:20",
  ["Mash very ripe bananas thoroughly.",
   "Whisk with flour, milk and eggs to a thick batter.",
   "Cook small pancakes in butter and serve with honey."],
  "The blacker the banana the better this gets - a true zero-waste recipe."),

 ("banana_smoothie", "Banana Almond Smoothie", "Continental", "breakfast", "vegetarian", 5, 2,
  "banana:240 milk:250 curd:100 honey:20 almond:20",
  ["Freeze overripe banana chunks in advance if you can.",
   "Blend everything until thick and smooth."],
  "Freeze spotty bananas instead of binning them, then blend later."),

 ("mango_lassi", "Mango Lassi", "North Indian", "snack", "vegetarian", 8, 2,
  "mango:300 curd:200 milk:100 sugar:20",
  ["Peel and chop ripe mango.",
   "Blend with curd, milk and sugar until frothy; chill before serving."],
  "Very soft mangoes are perfect here - texture stops mattering once blended."),

 ("fruit_chaat", "Fruit Chaat", "Indian", "snack", "vegan", 10, 3,
  "banana:200 apple:200 guava:150 pomegranate:100 lemon:20 salt:3",
  ["Dice all the fruit to a similar size.",
   "Toss with lemon, salt and a pinch of roasted cumin."],
  "Combines several fruits that are each too far gone to eat plain."),

 ("apple_cinnamon_oats", "Apple Cinnamon Oats", "Continental", "breakfast", "vegetarian", 12, 2,
  "oats:100 apple:200 milk:250 honey:20 walnut:20",
  ["Simmer oats in milk until creamy.",
   "Grate in the apple for the last two minutes.",
   "Top with honey and crushed walnuts."],
  "Grating rescues an apple that has gone soft or slightly bruised."),

 ("overnight_oats", "Overnight Oats", "Continental", "breakfast", "vegetarian", 5, 2,
  "oats:100 curd:200 banana:150 honey:20 almond:20",
  ["Layer oats, curd, sliced banana and honey in a jar.",
   "Refrigerate overnight; top with almonds before eating."],
  "Uses curd that is approaching its date - the tang is a feature."),

 ("paneer_tikka", "Paneer Tikka", "North Indian", "snack", "vegetarian", 35, 3,
  "paneer:250 curd:120 capsicum:100 onion:100 garam_masala:5 lemon:20",
  ["Whisk curd with spices and lemon into a thick marinade.",
   "Coat paneer, capsicum and onion chunks and rest 20 minutes.",
   "Grill, air-fry or pan-char until edges blacken."],
  "Rescues paneer and a tired capsicum in the same dish."),

 ("veg_hakka_noodles", "Veg Hakka Noodles", "Indo-Chinese", "dinner", "vegan", 20, 3,
  "noodles:250 cabbage:150 carrot:100 capsicum:80 spring_onion:50 garlic:15 cooking_oil:25",
  ["Boil noodles just until done, drain and toss with a little oil.",
   "Stir-fry garlic and julienned vegetables on the highest heat for 3 minutes.",
   "Add noodles and sauces, toss fast, finish with spring onion greens."],
  "Shredded vegetables cook so fast that even limp ones work."),

 ("pasta_arrabbiata", "Pasta Arrabbiata", "Italian", "dinner", "vegetarian", 25, 3,
  "pasta:250 tomato:500 garlic:20 olive_oil:30 cheese:50 chilli_powder:3",
  ["Simmer chopped tomatoes with garlic, chilli and olive oil for 15 minutes until jammy.",
   "Cook pasta and reserve a cup of the water.",
   "Toss pasta in the sauce with a splash of pasta water; grate cheese over."],
  "Half a kilo of soft tomatoes disappears into this sauce."),

 ("white_sauce_pasta", "White Sauce Pasta", "Italian", "dinner", "vegetarian", 30, 3,
  "pasta:250 milk:400 butter:30 maida:30 cheese:60 broccoli:150 capsicum:80",
  ["Make a roux with butter and flour, whisk in milk to a smooth bechamel.",
   "Melt in the cheese and season well.",
   "Fold in boiled pasta and blanched vegetables."],
  "Excellent use for milk on its last day - cooking it removes the risk of it turning."),

 ("mushroom_masala", "Mushroom Masala", "North Indian", "dinner", "vegetarian", 25, 3,
  "mushroom:300 onion:120 tomato:120 capsicum:80 garlic:12 cream:40?",
  ["Dry-saute mushrooms first to drive off their water, then set aside.",
   "Fry onion, garlic and tomato into a masala.",
   "Return mushrooms with capsicum, add cream and simmer briefly."],
  "Mushrooms are the most perishable item in the catalog - use within two days."),

 ("rajma_chawal", "Rajma Chawal", "North Indian", "dinner", "vegan", 60, 4,
  "rajma:200 rice:300 onion:150 tomato:200 ginger:15 garam_masala:6",
  ["Soak rajma overnight, then pressure cook until completely soft.",
   "Build an onion, tomato and ginger masala and add the beans with their stock.",
   "Simmer 20 minutes, mashing a few beans to thicken. Serve with rice."],
  "Pulses have long shelf lives - lean on them when fresh produce runs out."),

 ("chole_masala", "Chole Masala", "North Indian", "dinner", "vegan", 60, 4,
  "chole:200 onion:150 tomato:200 ginger:15 garam_masala:6 tea:2",
  ["Soak chickpeas overnight and boil with a tea bag for colour.",
   "Cook an onion, tomato and ginger masala until the oil separates.",
   "Add the chickpeas and stock, simmer 20 minutes."],
  "A pantry-only meal for the end of the week."),

 ("sprouts_salad", "Sprouts Salad", "Indian", "snack", "vegan", 10, 3,
  "sprouts:250 tomato:100 cucumber:100 onion:60 lemon:20 coriander:10",
  ["Steam sprouts 4 minutes if you prefer them soft.",
   "Toss with diced vegetables, lemon, salt and coriander."],
  "Sprouts spoil within days - eat them raw or steamed, fast."),

 ("cucumber_raita", "Cucumber Raita", "Indian", "lunch", "vegetarian", 8, 4,
  "curd:400 cucumber:200 mint:10 salt:4",
  ["Whisk curd smooth with a splash of water.",
   "Grate cucumber, squeeze out excess water, and fold in with mint and salt."],
  "Sour curd is fine here once whisked with salt and mint."),

 ("beetroot_carrot_salad", "Beetroot Carrot Salad", "South Indian", "lunch", "vegan", 15, 4,
  "beetroot:200 carrot:200 lemon:20 coconut:50 groundnut:30",
  ["Grate beetroot and carrot.",
   "Toss with lemon, salt, coconut and crushed roasted groundnuts."],
  "Root vegetables last weeks, so this is a reliable filler dish."),

 ("tomato_chutney", "Tomato Chutney", "South Indian", "condiment", "vegan", 20, 6,
  "tomato:400 garlic:15 green_chilli:10 curry_leaves:5 cooking_oil:25",
  ["Fry garlic, chilli and curry leaves, add tomato and salt.",
   "Cook down 12 minutes until thick and jammy, then blend coarsely."],
  "Turns a glut of soft tomatoes into something that keeps a week."),

 ("coriander_chutney", "Coriander Mint Chutney", "Indian", "condiment", "vegan", 10, 6,
  "coriander:80 mint:40 coconut:50 green_chilli:10 lemon:20",
  ["Blend everything with a little water and salt to a thick paste.",
   "Freeze in an ice tray for portions that keep a month."],
  "The definitive rescue for herbs - and it freezes, which fresh herbs do not."),

 ("veg_cutlet", "Vegetable Cutlet", "Indian", "snack", "vegetarian", 35, 4,
  "potato:300 carrot:100 peas_fresh:80 bread:80 besan:40 garam_masala:5",
  ["Boil and mash potato with cooked carrot and peas.",
   "Bind with breadcrumbs and besan, season well.",
   "Shape patties and shallow fry until crisp."],
  "Absorbs odds and ends of vegetables plus the heel of a bread loaf."),

 ("dosa_from_batter", "Dosa with Potato Masala", "South Indian", "breakfast", "vegan", 30, 4,
  "batter:600 potato:300 onion:120 curry_leaves:5 cooking_oil:30",
  ["Temper curry leaves, fry onion, add boiled crumbled potato with turmeric and salt.",
   "Spread batter thin on a hot tawa, drizzle oil and cook until crisp.",
   "Fill and fold."],
  "Batter sours quickly - once it smells sharp, use it the same day."),

 ("curd_rice", "Curd Rice", "South Indian", "lunch", "vegetarian", 15, 3,
  "cooked_rice:400 curd:300 curry_leaves:5 green_chilli:6 ginger:10 coconut:30?",
  ["Mash warm cooked rice slightly and cool it.",
   "Fold in curd with salt.",
   "Top with a tempering of curry leaves, chilli and ginger."],
  "Rescues leftover rice and sour curd together in one bowl."),

 ("dal_paratha", "Leftover Dal Paratha", "North Indian", "breakfast", "vegetarian", 30, 3,
  "cooked_dal:300 atta:250 cooking_oil:30 coriander:15",
  ["Knead thick leftover dal directly into the flour with coriander - add no water until needed.",
   "Rest the dough 15 minutes.",
   "Roll and cook on a tawa with oil."],
  "Turns yesterday's dal into today's breakfast with zero waste."),

 ("roti_churma", "Roti Churma", "Rajasthani", "snack", "vegetarian", 15, 3,
  "chapati_left:200 ghee:30 jaggery:60",
  ["Crush leftover rotis coarsely by hand or pulse briefly in a mixer.",
   "Roast the crumbs in ghee until fragrant.",
   "Stir in grated jaggery off the heat."],
  "A traditional dish invented specifically to use up dry leftover rotis."),

 ("veg_frittata", "Vegetable Frittata", "Continental", "dinner", "egg", 25, 3,
  "eggs:250 potato:200 capsicum:80 spring_onion:50 cheese:50 milk:60",
  ["Par-cook sliced potato in a pan.",
   "Beat eggs with milk, cheese and salt, pour over the vegetables.",
   "Cook on low until almost set, then finish under a grill."],
  "A frittata will absorb almost any leftover cooked vegetable."),

 ("sweet_corn_soup", "Sweet Corn Soup", "Indo-Chinese", "lunch", "vegan", 20, 3,
  "sweet_corn:250 carrot:80 cabbage:80 maida:20 spring_onion:40",
  ["Simmer corn and finely diced vegetables in stock for 10 minutes.",
   "Blend a third of the corn and return it for body.",
   "Thicken with a flour slurry and finish with spring onion."],
  "Uses the last of a cabbage and a couple of carrots."),

 ("papaya_smoothie", "Papaya Smoothie", "Continental", "breakfast", "vegetarian", 6, 2,
  "papaya:300 milk:200 honey:20 curd:100",
  ["Scoop out the papaya flesh, discarding seeds.",
   "Blend with milk, curd and honey until silky."],
  "Very ripe papaya is too soft to slice but ideal to blend."),

 ("watermelon_cooler", "Watermelon Cooler", "Indian", "snack", "vegan", 8, 3,
  "watermelon:600 lemon:25 mint:15 sugar:20?",
  ["Blend watermelon and strain lightly.",
   "Add lemon, muddled mint and a little salt; serve over ice."],
  "Cut watermelon dries out fast - juice it before it does."),

 ("grape_yogurt_bowl", "Grape Yogurt Bowl", "Continental", "snack", "vegetarian", 5, 2,
  "grapes:200 curd:200 honey:20 walnut:20",
  ["Halve the grapes.",
   "Layer with whisked curd, honey and crushed walnuts."],
  "Grapes that have gone soft still taste sweet in yogurt."),

 ("strawberry_milkshake", "Strawberry Milkshake", "Continental", "snack", "vegetarian", 6, 2,
  "strawberry:250 milk:300 sugar:25 ice_cream:100?",
  ["Hull the strawberries, discarding only truly mouldy fruit.",
   "Blend with cold milk and sugar until frothy."],
  "Strawberries last barely three days - blend them on day three."),

 ("lemon_rice", "Lemon Rice", "South Indian", "lunch", "vegan", 15, 3,
  "cooked_rice:400 lemon:40 groundnut:40 curry_leaves:5 turmeric:3 green_chilli:8",
  ["Temper groundnuts, curry leaves, chilli and turmeric in oil.",
   "Fold in cold cooked rice gently so grains stay separate.",
   "Finish with plenty of lemon juice off the heat."],
  "Second-best use of leftover rice after fried rice, and faster."),
]


def main():
    catalog_path = os.path.join(HERE, "food_catalog.csv")
    valid = {r["id"] for r in csv.DictReader(open(catalog_path))}

    recipes = []
    problems = []
    for rid, title, cuisine, meal, diet, minutes, servings, spec, steps, note in R:
        ingredients = ing(spec)
        for i in ingredients:
            if i["id"] not in valid:
                problems.append((rid, i["id"]))
        recipes.append({
            "id": rid,
            "title": title,
            "cuisine": cuisine,
            "meal": meal,
            "diet": diet,
            "minutes": minutes,
            "servings": servings,
            "ingredients": ingredients,
            "steps": steps,
            "rescue_note": note,
        })

    if problems:
        raise SystemExit("Unknown ingredient ids: %s" % problems)

    ids = [r["id"] for r in recipes]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate recipe ids")

    out = os.path.join(HERE, "recipes.json")
    with open(out, "w") as fh:
        json.dump(recipes, fh, indent=1, ensure_ascii=True)
    print("wrote %d recipes -> %s" % (len(recipes), out))
    print("distinct ingredients used: %d of %d catalog foods" % (
        len({i["id"] for r in recipes for i in r["ingredients"]}), len(valid)))


if __name__ == "__main__":
    main()
