export interface CakeTemplate {
    id: string;
    name: string;
    category:
      | "Birthday"
      | "Wedding"
      | "Baby Shower"
      | "Graduation"
      | "Corporate";
  
    image: string;
    description: string;
  
    shape: "Round" | "Rectangle" | "Number" | "Cloud";
    tiers: number;
  
    premium: boolean;
  
    featured?: boolean;
    difficulty?: "Easy" | "Medium" | "Advanced";
    tags?: string[];
  }
  
  export const cakeTemplates: CakeTemplate[] = [
  
    // =====================================================
    // BIRTHDAY
    // =====================================================
  
    {
      id: "gold-leaf-romance",
      name: "Gold Leaf Romance",
      category: "Birthday",
      image: "/assets/images/templates/gold-leaf-romance-v1.png",
      description: "Luxury ivory birthday cake with cascading gold leaf and handcrafted floral details.",
      shape: "Round",
      tiers: 3,
      premium: true,
      featured: true,
      difficulty: "Advanced",
      tags: ["birthday","gold","ivory","luxury","floral","premium","elegant"]
    },
  
    {
      id: "ivory-three-tier-classic",
      name: "Ivory Three-Tier Classic",
      category: "Birthday",
      image: "/assets/images/templates/ivory-three-tier-classic-v1.png",
      description: "Timeless French three-tier celebration cake with handcrafted ivory buttercream.",
      shape: "Round",
      tiers: 3,
      premium: true,
      featured: true,
      difficulty: "Advanced",
      tags: ["birthday","classic","ivory","three-tier","luxury","flowers"]
    },
  
    {
      id: "class-of-photo-cake",
      name: "Classic Photo Cake",
      category: "Birthday",
      image: "/assets/images/templates/class-of-photo-cake-v1.png",
      description: "Elegant rectangular birthday cake featuring a premium edible photo centerpiece.",
      shape: "Rectangle",
      tiers: 1,
      premium: true,
      featured: false,
      difficulty: "Medium",
      tags: ["birthday","photo","rectangle","minimal","modern"]
    },
  
    // =====================================================
    // WEDDING
    // =====================================================
  
    {
      id: "naked-cake-garden",
      name: "Naked Cake Garden",
      category: "Wedding",
      image: "/assets/images/templates/naked-cake-garden-v1.png",
      description: "Romantic semi-naked wedding cake decorated with fresh garden flowers.",
      shape: "Round",
      tiers: 3,
      premium: true,
      featured: true,
      difficulty: "Medium",
      tags: ["wedding","garden","naked","flowers","romantic","luxury"]
    },
  
    {
      id: "soft-blush-blossom",
      name: "Soft Blush Blossom",
      category: "Wedding",
      image: "/assets/images/templates/soft-blush-blossom-v1.png",
      description: "Minimal blush ombré wedding cake with handcrafted floral artistry.",
      shape: "Round",
      tiers: 1,
      premium: true,
      featured: true,
      difficulty: "Medium",
      tags: ["wedding","blush","ombre","minimal","flowers","luxury"]
    },
  
    {
      id: "executive-monogram-cake",
      name: "Executive Monogram Cake",
      category: "Wedding",
      image: "/assets/images/templates/executive-monogram-cake-v1.png",
      description: "Architectural wedding cake inspired by modern Art Deco elegance.",
      shape: "Rectangle",
      tiers: 1,
      premium: true,
      featured: true,
      difficulty: "Advanced",
      tags: ["wedding","modern","art-deco","rectangle","luxury","monogram"]
    },
  
    // =====================================================
    // BABY SHOWER
    // =====================================================
  
    {
      id: "little-feet-delight",
      name: "Little Feet Delight",
      category: "Baby Shower",
      image: "/assets/images/templates/little-feet-delight-v1.png",
      description: "Elegant ivory baby shower cake with handcrafted fondant baby footprints.",
      shape: "Round",
      tiers: 1,
      premium: true,
      featured: true,
      difficulty: "Medium",
      tags: ["baby","footprints","ivory","minimal","luxury","flowers"]
    },
  
    {
      id: "soft-blush-baby",
      name: "Soft Blush Baby",
      category: "Baby Shower",
      image: "/assets/images/templates/soft-blush-blossom-v1.png",
      description: "Soft blush floral baby shower cake inspired by timeless French pâtisserie.",
      shape: "Round",
      tiers: 1,
      premium: true,
      featured: false,
      difficulty: "Medium",
      tags: ["baby","blush","flowers","ivory","romantic"]
    },
  
    {
      id: "storybook-baby-cloud",
      name: "Storybook Baby Cloud",
      category: "Baby Shower",
      image: "/assets/images/templates/storybook-baby-cloud-v1.png",
      description: "Dreamlike cloud-shaped baby shower cake with delicate gold stars.",
      shape: "Cloud",
      tiers: 1,
      premium: true,
      featured: true,
      difficulty: "Advanced",
      tags: ["baby","cloud","storybook","stars","dream","luxury"]
    },
  
    // =====================================================
    // GRADUATION
    // =====================================================
  
    {
      id: "cap-diploma-classic",
      name: "Cap & Diploma Classic",
      category: "Graduation",
      image: "/assets/images/templates/cap-diploma-classic-v1.png",
      description: "Classic graduation cake with handcrafted diploma and graduation cap.",
      shape: "Round",
      tiers: 1,
      premium: true,
      featured: true,
      difficulty: "Medium",
      tags: ["graduation","cap","diploma","classic","flowers"]
    },
  
    {
      id: "golden-achievement-cake",
      name: "Golden Achievement Cake",
      category: "Graduation",
      image: "/assets/images/templates/golden-achievement-cake-v1.png",
      description: "Luxury graduation cake featuring an elegant sculptural golden award.",
      shape: "Round",
      tiers: 1,
      premium: true,
      featured: true,
      difficulty: "Advanced",
      tags: ["graduation","award","gold","luxury","achievement"]
    },
  
    {
      id: "luxury-abstract-architecture",
      name: "Luxury Abstract Architecture",
      category: "Graduation",
      image: "/assets/images/templates/luxury-abstract-corporate-celebration-v1.png",
      description: "Architectural multi-tier cake inspired by contemporary luxury design.",
      shape: "Round",
      tiers: 4,
      premium: true,
      featured: true,
      difficulty: "Advanced",
      tags: ["graduation","architecture","modern","gold","minimal","premium"]
    },
  
    // =====================================================
    // CORPORATE
    // =====================================================
  
    {
      id: "product-launch-centerpiece",
      name: "Product Launch Centerpiece",
      category: "Corporate",
      image: "/assets/images/templates/product-launch-centerpiece-v1.png",
      description: "Luxury corporate cake with a clean presentation area for product launches.",
      shape: "Rectangle",
      tiers: 1,
      premium: true,
      featured: true,
      difficulty: "Advanced",
      tags: ["corporate","launch","branding","rectangle","modern","luxury"]
    },
  
    {
      id: "executive-award",
      name: "Executive Award",
      category: "Corporate",
      image: "/assets/images/templates/golden-achievement-cake-v1.png",
      description: "Executive recognition cake celebrating excellence with refined gold detailing.",
      shape: "Round",
      tiers: 1,
      premium: true,
      featured: false,
      difficulty: "Advanced",
      tags: ["corporate","award","gold","executive","premium"]
    },
  
    {
      id: "executive-art-deco",
      name: "Executive Art Deco",
      category: "Corporate",
      image: "/assets/images/templates/luxury-abstract-corporate-celebration-v1.png",
      description: "Luxury corporate centerpiece featuring elegant Art Deco architectural styling.",
      shape: "Round",
      tiers: 4,
      premium: true,
      featured: true,
      difficulty: "Advanced",
      tags: ["corporate","art-deco","architecture","gold","modern","premium"]
    }
  
  ];
  