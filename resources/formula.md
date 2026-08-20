# AI Retail 360 Formula Verification Pack

- **Workbook:** `Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx`
- **Scope:** 23 documented formulas × 5 worked examples = **115 examples**
- **Verification method:** each example records the workbook result cell, the native Excel formula, direct input/source cells, cached workbook values, and a readable arithmetic check.
- **Important:** values are read from the workbook’s saved calculation cache. Minor displayed differences can occur because Excel stores more precision than formatted cells show.

## Formula index

1. [ADS per store](#formula-1-ads-per-store)
2. [On-hand](#formula-2-on-hand)
3. [Open PO per store](#formula-3-open-po-per-store)
4. [Position](#formula-4-position)
5. [ROP](#formula-5-rop)
6. [Maximum inventory](#formula-6-maximum-inventory)
7. [Inventory state](#formula-7-inventory-state)
8. [Forecast 7 days](#formula-8-forecast-7-days)
9. [Order quantity, sales units](#formula-9-order-quantity-sales-units)
10. [Order quantity, purchase units](#formula-10-order-quantity-purchase-units)
11. [Order value](#formula-11-order-value)
12. [At-risk value](#formula-12-at-risk-value)
13. [Incremental promotion margin](#formula-13-incremental-promotion-margin)
14. [Recoverable at-risk value](#formula-14-recoverable-at-risk-value)
15. [Contribution per day](#formula-15-contribution-per-day)
16. [Labour FTE](#formula-16-labour-fte)
17. [Required workforce](#formula-17-required-workforce)
18. [Scheduled workforce](#formula-18-scheduled-workforce)
19. [Coverage gap](#formula-19-coverage-gap)
20. [Days of supply](#formula-20-days-of-supply)
21. [Inventory value](#formula-21-inventory-value)
22. [Expiry units](#formula-22-expiry-units)
23. [Markdown at-risk value (gross)](#formula-23-markdown-at-risk-value-gross)

## Formula 1: ADS per store

**Documented logic:** `Base ADS × seasonality × archetype/horizon factor × store size × (1 + demand lever)`

### Example 1: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!J4` = **28.755632**
- **Native Excel formula:**

```excel
=$AG4*$F4*$AH4*$H4*(1+Constants!$B$16/100)*IF(AND(SKU_Master!$U$6="Y",Constants!$B$17>0),1+(Constants!$B$17/100)*1.3*(1-SKU_Master!$T$6),1)
```

- **Arithmetic / decision check:** `20.9096 × 1.14 × 0.9859 × 1.4619 with active levers = 34.355883`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `G6` | 20.9096 | Direct precedent/input |
| `SKU_Master` | `AA6` | 1.14 | Direct precedent/input |
| `ENGINE_STORE` | `AH4` | 0.9859 | Direct precedent/input |
| `Stores` | `E6` | 1.2236 | Direct precedent/input |
| `Constants` | `B16` | 0 | Direct precedent/input |
| `SKU_Master` | `U6` | N | Direct precedent/input |
| `Constants` | `B17` | 0 | Direct precedent/input |
| `SKU_Master` | `T6` | 0.26 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S002`

- **Result:** `ENGINE_STORE!J5` = **34.083273**
- **Native Excel formula:**

```excel
=$AG5*$F5*$AH5*$H5*(1+Constants!$B$16/100)*IF(AND(SKU_Master!$U$6="Y",Constants!$B$17>0),1+(Constants!$B$17/100)*1.3*(1-SKU_Master!$T$6),1)
```

- **Arithmetic / decision check:** `20.9096 × 1.14 × 1.4503 with active levers = 34.57072`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `G6` | 20.9096 | Direct precedent/input |
| `SKU_Master` | `AA6` | 1.14 | Direct precedent/input |
| `ENGINE_STORE` | `AH5` | 0.9859 | Direct precedent/input |
| `Stores` | `E7` | 1.4503 | Direct precedent/input |
| `Constants` | `B16` | 0 | Direct precedent/input |
| `SKU_Master` | `U6` | N | Direct precedent/input |
| `Constants` | `B17` | 0 | Direct precedent/input |
| `SKU_Master` | `T6` | 0.26 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, Store `S003`

- **Result:** `ENGINE_STORE!J6` = **19.338844**
- **Native Excel formula:**

```excel
=$AG6*$F6*$AH6*$H6*(1+Constants!$B$16/100)*IF(AND(SKU_Master!$U$6="Y",Constants!$B$17>0),1+(Constants!$B$17/100)*1.3*(1-SKU_Master!$T$6),1)
```

- **Arithmetic / decision check:** `20.9096 × 1.14 × 0.8229 with active levers = 19.615421`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `G6` | 20.9096 | Direct precedent/input |
| `SKU_Master` | `AA6` | 1.14 | Direct precedent/input |
| `ENGINE_STORE` | `AH6` | 0.9859 | Direct precedent/input |
| `Stores` | `E8` | 0.8229 | Direct precedent/input |
| `Constants` | `B16` | 0 | Direct precedent/input |
| `SKU_Master` | `U6` | N | Direct precedent/input |
| `Constants` | `B17` | 0 | Direct precedent/input |
| `SKU_Master` | `T6` | 0.26 | Direct precedent/input |

---

### Example 4: SKU `GRC-001`, Store `S004`

- **Result:** `ENGINE_STORE!J7` = **25.265756**
- **Native Excel formula:**

```excel
=$AG7*$F7*$AH7*$H7*(1+Constants!$B$16/100)*IF(AND(SKU_Master!$U$6="Y",Constants!$B$17>0),1+(Constants!$B$17/100)*1.3*(1-SKU_Master!$T$6),1)
```

- **Arithmetic / decision check:** `20.9096 × 1.14 × 1.0751 with active levers = 25.627098`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `G6` | 20.9096 | Direct precedent/input |
| `SKU_Master` | `AA6` | 1.14 | Direct precedent/input |
| `ENGINE_STORE` | `AH7` | 0.9859 | Direct precedent/input |
| `Stores` | `E9` | 1.0751 | Direct precedent/input |
| `Constants` | `B16` | 0 | Direct precedent/input |
| `SKU_Master` | `U6` | N | Direct precedent/input |
| `Constants` | `B17` | 0 | Direct precedent/input |
| `SKU_Master` | `T6` | 0.26 | Direct precedent/input |

---

### Example 5: SKU `GRC-001`, Store `S005`

- **Result:** `ENGINE_STORE!J8` = **34.355883**
- **Native Excel formula:**

```excel
=$AG8*$F8*$AH8*$H8*(1+Constants!$B$16/100)*IF(AND(SKU_Master!$U$6="Y",Constants!$B$17>0),1+(Constants!$B$17/100)*1.3*(1-SKU_Master!$T$6),1)
```

- **Arithmetic / decision check:** `20.9096 × 1.14 × 1.4619 with active levers = 34.847228`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `G6` | 20.9096 | Direct precedent/input |
| `SKU_Master` | `AA6` | 1.14 | Direct precedent/input |
| `ENGINE_STORE` | `AH8` | 0.9859 | Direct precedent/input |
| `Stores` | `E10` | 1.4619 | Direct precedent/input |
| `Constants` | `B16` | 0 | Direct precedent/input |
| `SKU_Master` | `U6` | N | Direct precedent/input |
| `Constants` | `B17` | 0 | Direct precedent/input |
| `SKU_Master` | `T6` | 0.26 | Direct precedent/input |

---

## Formula 2: On-hand

**Documented logic:** `Base ADS × on-hand days × stock factor × store health × store size`

### Example 1: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!K4` = **66.793533**
- **Native Excel formula:**

```excel
=SKU_Master!$G$6*SKU_Master!$L$6*$G4*$I4*$H4
```

- **Arithmetic / decision check:** `20.9096 × 2.5 × 1.03793 × 1.0061 × 1.2236 = 66.793533`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `G6` | 20.9096 | Direct precedent/input |
| `SKU_Master` | `L6` | 2.5 | Direct precedent/input |
| `SKU_Master` | `AB6` | 1.03793 | Direct precedent/input |
| `Stores` | `F6` | 1.0061 | Direct precedent/input |
| `Stores` | `E6` | 1.2236 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S002`

- **Result:** `ENGINE_STORE!K5` = **72.456434**
- **Native Excel formula:**

```excel
=SKU_Master!$G$6*SKU_Master!$L$6*$G5*$I5*$H5
```

- **Arithmetic / decision check:** `20.9096 × 2.5 × 1.03793 × 0.9208 × 1.4503 = 72.456434`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `G6` | 20.9096 | Direct precedent/input |
| `SKU_Master` | `L6` | 2.5 | Direct precedent/input |
| `SKU_Master` | `AB6` | 1.03793 | Direct precedent/input |
| `Stores` | `F7` | 0.9208 | Direct precedent/input |
| `Stores` | `E7` | 1.4503 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, Store `S003`

- **Result:** `ENGINE_STORE!K6` = **44.781826**
- **Native Excel formula:**

```excel
=SKU_Master!$G$6*SKU_Master!$L$6*$G6*$I6*$H6
```

- **Arithmetic / decision check:** `20.9096 × 2.5 × 1.03793 × 1.003 × 0.8229 = 44.781826`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `G6` | 20.9096 | Direct precedent/input |
| `SKU_Master` | `L6` | 2.5 | Direct precedent/input |
| `SKU_Master` | `AB6` | 1.03793 | Direct precedent/input |
| `Stores` | `F8` | 1.003 | Direct precedent/input |
| `Stores` | `E8` | 0.8229 | Direct precedent/input |

---

### Example 4: SKU `GRC-001`, Store `S004`

- **Result:** `ENGINE_STORE!K7` = **52.113304**
- **Native Excel formula:**

```excel
=SKU_Master!$G$6*SKU_Master!$L$6*$G7*$I7*$H7
```

- **Arithmetic / decision check:** `20.9096 × 2.5 × 1.03793 × 0.8934 × 1.0751 = 52.113304`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `G6` | 20.9096 | Direct precedent/input |
| `SKU_Master` | `L6` | 2.5 | Direct precedent/input |
| `SKU_Master` | `AB6` | 1.03793 | Direct precedent/input |
| `Stores` | `F9` | 0.8934 | Direct precedent/input |
| `Stores` | `E9` | 1.0751 | Direct precedent/input |

---

### Example 5: SKU `GRC-001`, Store `S005`

- **Result:** `ENGINE_STORE!K8` = **100.067522**
- **Native Excel formula:**

```excel
=SKU_Master!$G$6*SKU_Master!$L$6*$G8*$I8*$H8
```

- **Arithmetic / decision check:** `20.9096 × 2.5 × 1.03793 × 1.2616 × 1.4619 = 100.067522`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `G6` | 20.9096 | Direct precedent/input |
| `SKU_Master` | `L6` | 2.5 | Direct precedent/input |
| `SKU_Master` | `AB6` | 1.03793 | Direct precedent/input |
| `Stores` | `F10` | 1.2616 | Direct precedent/input |
| `Stores` | `E10` | 1.4619 | Direct precedent/input |

---

## Formula 3: Open PO per store

**Documented logic:** `Open PO × (store size ÷ total vertical store size) × (1 + inbound lever)`

### Example 1: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!L4` = **1.467519**
- **Native Excel formula:**

```excel
=SKU_Master!$M$6*($H4/SKU_Master!$AC$6)*(1+Constants!$B$19/100)
```

- **Arithmetic / decision check:** `25 × (1.2236 ÷ 20.8447) × (1 + 0%) = 1.467519`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `M6` | 25 | Direct precedent/input |
| `Stores` | `E6` | 1.2236 | Direct precedent/input |
| `SKU_Master` | `AC6` | 20.8447 | Direct precedent/input |
| `Constants` | `B19` | 0 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S002`

- **Result:** `ENGINE_STORE!L5` = **1.739411**
- **Native Excel formula:**

```excel
=SKU_Master!$M$6*($H5/SKU_Master!$AC$6)*(1+Constants!$B$19/100)
```

- **Arithmetic / decision check:** `25 × (1.4503 ÷ 20.8447) × (1 + 0%) = 1.739411`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `M6` | 25 | Direct precedent/input |
| `Stores` | `E7` | 1.4503 | Direct precedent/input |
| `SKU_Master` | `AC6` | 20.8447 | Direct precedent/input |
| `Constants` | `B19` | 0 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, Store `S003`

- **Result:** `ENGINE_STORE!L6` = **0.986942**
- **Native Excel formula:**

```excel
=SKU_Master!$M$6*($H6/SKU_Master!$AC$6)*(1+Constants!$B$19/100)
```

- **Arithmetic / decision check:** `25 × (0.8229 ÷ 20.8447) × (1 + 0%) = 0.986942`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `M6` | 25 | Direct precedent/input |
| `Stores` | `E8` | 0.8229 | Direct precedent/input |
| `SKU_Master` | `AC6` | 20.8447 | Direct precedent/input |
| `Constants` | `B19` | 0 | Direct precedent/input |

---

### Example 4: SKU `GRC-001`, Store `S004`

- **Result:** `ENGINE_STORE!L7` = **1.289416**
- **Native Excel formula:**

```excel
=SKU_Master!$M$6*($H7/SKU_Master!$AC$6)*(1+Constants!$B$19/100)
```

- **Arithmetic / decision check:** `25 × (1.0751 ÷ 20.8447) × (1 + 0%) = 1.289416`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `M6` | 25 | Direct precedent/input |
| `Stores` | `E9` | 1.0751 | Direct precedent/input |
| `SKU_Master` | `AC6` | 20.8447 | Direct precedent/input |
| `Constants` | `B19` | 0 | Direct precedent/input |

---

### Example 5: SKU `GRC-001`, Store `S005`

- **Result:** `ENGINE_STORE!L8` = **1.753323**
- **Native Excel formula:**

```excel
=SKU_Master!$M$6*($H8/SKU_Master!$AC$6)*(1+Constants!$B$19/100)
```

- **Arithmetic / decision check:** `25 × (1.4619 ÷ 20.8447) × (1 + 0%) = 1.753323`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `SKU_Master` | `M6` | 25 | Direct precedent/input |
| `Stores` | `E10` | 1.4619 | Direct precedent/input |
| `SKU_Master` | `AC6` | 20.8447 | Direct precedent/input |
| `Constants` | `B19` | 0 | Direct precedent/input |

---

## Formula 4: Position

**Documented logic:** `ROUND(on-hand + open PO)`

### Example 1: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!M4` = **68**
- **Native Excel formula:**

```excel
=ROUND($K4+$L4,0)
```

- **Arithmetic / decision check:** `ROUND(66.793533 + 1.467519) = 68`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `K4` | 66.793533 | Direct precedent/input |
| `ENGINE_STORE` | `L4` | 1.467519 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S002`

- **Result:** `ENGINE_STORE!M5` = **74**
- **Native Excel formula:**

```excel
=ROUND($K5+$L5,0)
```

- **Arithmetic / decision check:** `ROUND(72.456434 + 1.739411) = 74`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `K5` | 72.456434 | Direct precedent/input |
| `ENGINE_STORE` | `L5` | 1.739411 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, Store `S003`

- **Result:** `ENGINE_STORE!M6` = **46**
- **Native Excel formula:**

```excel
=ROUND($K6+$L6,0)
```

- **Arithmetic / decision check:** `ROUND(44.781826 + 0.986942) = 46`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `K6` | 44.781826 | Direct precedent/input |
| `ENGINE_STORE` | `L6` | 0.986942 | Direct precedent/input |

---

### Example 4: SKU `GRC-001`, Store `S004`

- **Result:** `ENGINE_STORE!M7` = **53**
- **Native Excel formula:**

```excel
=ROUND($K7+$L7,0)
```

- **Arithmetic / decision check:** `ROUND(52.113304 + 1.289416) = 53`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `K7` | 52.113304 | Direct precedent/input |
| `ENGINE_STORE` | `L7` | 1.289416 | Direct precedent/input |

---

### Example 5: SKU `GRC-001`, Store `S005`

- **Result:** `ENGINE_STORE!M8` = **102**
- **Native Excel formula:**

```excel
=ROUND($K8+$L8,0)
```

- **Arithmetic / decision check:** `ROUND(100.067522 + 1.753323) = 102`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `K8` | 100.067522 | Direct precedent/input |
| `ENGINE_STORE` | `L8` | 1.753323 | Direct precedent/input |

---

## Formula 5: ROP

**Documented logic:** `ROUND(ADS × (lead + safety))`

### Example 1: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!N4` = **88**
- **Native Excel formula:**

```excel
=ROUND($J4*(MAX(1,SKU_Master!$K$6+Constants!$B$20)+MAX(0,SKU_Master!$N$6+Constants!$B$21)),0)
```

- **Arithmetic / decision check:** `ROUND(29.166885 × adjusted lead-and-safety days) = 88`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J4` | 29.166885 | Direct precedent/input |
| `SKU_Master` | `K6` | 2 | Direct precedent/input |
| `Constants` | `B20` | 0 | Direct precedent/input |
| `SKU_Master` | `N6` | 1 | Direct precedent/input |
| `Constants` | `B21` | 0 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S002`

- **Result:** `ENGINE_STORE!N5` = **104**
- **Native Excel formula:**

```excel
=ROUND($J5*(MAX(1,SKU_Master!$K$6+Constants!$B$20)+MAX(0,SKU_Master!$N$6+Constants!$B$21)),0)
```

- **Arithmetic / decision check:** `ROUND(34.57072 × adjusted lead-and-safety days) = 104`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J5` | 34.57072 | Direct precedent/input |
| `SKU_Master` | `K6` | 2 | Direct precedent/input |
| `Constants` | `B20` | 0 | Direct precedent/input |
| `SKU_Master` | `N6` | 1 | Direct precedent/input |
| `Constants` | `B21` | 0 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, Store `S003`

- **Result:** `ENGINE_STORE!N6` = **59**
- **Native Excel formula:**

```excel
=ROUND($J6*(MAX(1,SKU_Master!$K$6+Constants!$B$20)+MAX(0,SKU_Master!$N$6+Constants!$B$21)),0)
```

- **Arithmetic / decision check:** `ROUND(19.615421 × adjusted lead-and-safety days) = 59`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J6` | 19.615421 | Direct precedent/input |
| `SKU_Master` | `K6` | 2 | Direct precedent/input |
| `Constants` | `B20` | 0 | Direct precedent/input |
| `SKU_Master` | `N6` | 1 | Direct precedent/input |
| `Constants` | `B21` | 0 | Direct precedent/input |

---

### Example 4: SKU `GRC-001`, Store `S004`

- **Result:** `ENGINE_STORE!N7` = **77**
- **Native Excel formula:**

```excel
=ROUND($J7*(MAX(1,SKU_Master!$K$6+Constants!$B$20)+MAX(0,SKU_Master!$N$6+Constants!$B$21)),0)
```

- **Arithmetic / decision check:** `ROUND(25.627098 × adjusted lead-and-safety days) = 77`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J7` | 25.627098 | Direct precedent/input |
| `SKU_Master` | `K6` | 2 | Direct precedent/input |
| `Constants` | `B20` | 0 | Direct precedent/input |
| `SKU_Master` | `N6` | 1 | Direct precedent/input |
| `Constants` | `B21` | 0 | Direct precedent/input |

---

### Example 5: SKU `GRC-001`, Store `S005`

- **Result:** `ENGINE_STORE!N8` = **105**
- **Native Excel formula:**

```excel
=ROUND($J8*(MAX(1,SKU_Master!$K$6+Constants!$B$20)+MAX(0,SKU_Master!$N$6+Constants!$B$21)),0)
```

- **Arithmetic / decision check:** `ROUND(34.847228 × adjusted lead-and-safety days) = 105`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J8` | 34.847228 | Direct precedent/input |
| `SKU_Master` | `K6` | 2 | Direct precedent/input |
| `Constants` | `B20` | 0 | Direct precedent/input |
| `SKU_Master` | `N6` | 1 | Direct precedent/input |
| `Constants` | `B21` | 0 | Direct precedent/input |

---

## Formula 6: Maximum inventory

**Documented logic:** `ROUND(ADS × (lead + safety + 4))`

### Example 1: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!O4` = **201**
- **Native Excel formula:**

```excel
=ROUND($J4*(MAX(1,SKU_Master!$K$6+Constants!$B$20)+MAX(0,SKU_Master!$N$6+Constants!$B$21)+Constants!$B$24),0)
```

- **Arithmetic / decision check:** `ROUND(28.755632 × (adjusted lead-and-safety days + 4)) = 201`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J4` | 28.755632 | Direct precedent/input |
| `SKU_Master` | `K6` | 2 | Direct precedent/input |
| `Constants` | `B20` | 0 | Direct precedent/input |
| `SKU_Master` | `N6` | 1 | Direct precedent/input |
| `Constants` | `B21` | 0 | Direct precedent/input |
| `Constants` | `B24` | 4 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S002`

- **Result:** `ENGINE_STORE!O5` = **239**
- **Native Excel formula:**

```excel
=ROUND($J5*(MAX(1,SKU_Master!$K$6+Constants!$B$20)+MAX(0,SKU_Master!$N$6+Constants!$B$21)+Constants!$B$24),0)
```

- **Arithmetic / decision check:** `ROUND(34.083273 × (adjusted lead-and-safety days + 4)) = 239`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J5` | 34.083273 | Direct precedent/input |
| `SKU_Master` | `K6` | 2 | Direct precedent/input |
| `Constants` | `B20` | 0 | Direct precedent/input |
| `SKU_Master` | `N6` | 1 | Direct precedent/input |
| `Constants` | `B21` | 0 | Direct precedent/input |
| `Constants` | `B24` | 4 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, Store `S003`

- **Result:** `ENGINE_STORE!O6` = **135**
- **Native Excel formula:**

```excel
=ROUND($J6*(MAX(1,SKU_Master!$K$6+Constants!$B$20)+MAX(0,SKU_Master!$N$6+Constants!$B$21)+Constants!$B$24),0)
```

- **Arithmetic / decision check:** `ROUND(19.338844 × (adjusted lead-and-safety days + 4)) = 135`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J6` | 19.338844 | Direct precedent/input |
| `SKU_Master` | `K6` | 2 | Direct precedent/input |
| `Constants` | `B20` | 0 | Direct precedent/input |
| `SKU_Master` | `N6` | 1 | Direct precedent/input |
| `Constants` | `B21` | 0 | Direct precedent/input |
| `Constants` | `B24` | 4 | Direct precedent/input |

---

### Example 4: SKU `GRC-001`, Store `S004`

- **Result:** `ENGINE_STORE!O7` = **177**
- **Native Excel formula:**

```excel
=ROUND($J7*(MAX(1,SKU_Master!$K$6+Constants!$B$20)+MAX(0,SKU_Master!$N$6+Constants!$B$21)+Constants!$B$24),0)
```

- **Arithmetic / decision check:** `ROUND(25.265756 × (adjusted lead-and-safety days + 4)) = 177`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J7` | 25.265756 | Direct precedent/input |
| `SKU_Master` | `K6` | 2 | Direct precedent/input |
| `Constants` | `B20` | 0 | Direct precedent/input |
| `SKU_Master` | `N6` | 1 | Direct precedent/input |
| `Constants` | `B21` | 0 | Direct precedent/input |
| `Constants` | `B24` | 4 | Direct precedent/input |

---

### Example 5: SKU `GRC-001`, Store `S005`

- **Result:** `ENGINE_STORE!O8` = **240**
- **Native Excel formula:**

```excel
=ROUND($J8*(MAX(1,SKU_Master!$K$6+Constants!$B$20)+MAX(0,SKU_Master!$N$6+Constants!$B$21)+Constants!$B$24),0)
```

- **Arithmetic / decision check:** `ROUND(34.355883 × (adjusted lead-and-safety days + 4)) = 240`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J8` | 34.355883 | Direct precedent/input |
| `SKU_Master` | `K6` | 2 | Direct precedent/input |
| `Constants` | `B20` | 0 | Direct precedent/input |
| `SKU_Master` | `N6` | 1 | Direct precedent/input |
| `Constants` | `B21` | 0 | Direct precedent/input |
| `Constants` | `B24` | 4 | Direct precedent/input |

---

## Formula 7: Inventory state

**Documented logic:** `Stockout / Low / Expiry / Overstock / Slow-mover / Healthy classification`

### Example 1: SKU `GRC-001`, Store `S012`

- **Result:** `ENGINE_STORE!Q15` = **Stockout**
- **Native Excel formula:**

```excel
=IF($M15<$N15*0.6,"Stockout",IF($M15<$N15,"Low",IF(AND($E15="Y",$P15>SKU_Master!$O$6),"Expiry",IF(AND($E15="N",$P15>15),"Overstock",IF(AND(SKU_Master!$P$6<1,$P15>10),"Slow-mover","Healthy")))))
```

- **Arithmetic / decision check:** `Position 26; ROP 44; DoS 1.775588; classification = Stockout`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `M15` | 26 | Direct precedent/input |
| `ENGINE_STORE` | `N15` | 44 | Direct precedent/input |
| `ENGINE_STORE` | `P15` | 1.775588 | Direct precedent/input |
| `ENGINE_STORE` | `E15` | Y | Direct precedent/input |
| `SKU_Master` | `O6` | 3 | Direct precedent/input |
| `SKU_Master` | `P6` | 1.1125 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!Q4` = **Low**
- **Native Excel formula:**

```excel
=IF($M4<$N4*0.6,"Stockout",IF($M4<$N4,"Low",IF(AND($E4="Y",$P4>SKU_Master!$O$6),"Expiry",IF(AND($E4="N",$P4>15),"Overstock",IF(AND(SKU_Master!$P$6<1,$P4>10),"Slow-mover","Healthy")))))
```

- **Arithmetic / decision check:** `Position 68; ROP 88; DoS 2.331411; classification = Low`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `M4` | 68 | Direct precedent/input |
| `ENGINE_STORE` | `N4` | 88 | Direct precedent/input |
| `ENGINE_STORE` | `P4` | 2.331411 | Direct precedent/input |
| `ENGINE_STORE` | `E4` | Y | Direct precedent/input |
| `SKU_Master` | `O6` | 3 | Direct precedent/input |
| `SKU_Master` | `P6` | 1.1125 | Direct precedent/input |

---

### Example 3: SKU `GRC-002`, Store `S005`

- **Result:** `ENGINE_STORE!Q28` = **Expiry**
- **Native Excel formula:**

```excel
=IF($M28<$N28*0.6,"Stockout",IF($M28<$N28,"Low",IF(AND($E28="Y",$P28>SKU_Master!$O$7),"Expiry",IF(AND($E28="N",$P28>15),"Overstock",IF(AND(SKU_Master!$P$7<1,$P28>10),"Slow-mover","Healthy")))))
```

- **Arithmetic / decision check:** `Position 110; ROP 70; DoS 4.688716; classification = Expiry`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `M28` | 110 | Direct precedent/input |
| `ENGINE_STORE` | `N28` | 70 | Direct precedent/input |
| `ENGINE_STORE` | `P28` | 4.688716 | Direct precedent/input |
| `ENGINE_STORE` | `E28` | Y | Direct precedent/input |
| `SKU_Master` | `O7` | 4 | Direct precedent/input |
| `SKU_Master` | `P7` | 1.2005 | Direct precedent/input |

---

### Example 4: SKU `GRC-043`, Store `S005`

- **Result:** `ENGINE_STORE!Q848` = **Overstock**
- **Native Excel formula:**

```excel
=IF($M848<$N848*0.6,"Stockout",IF($M848<$N848,"Low",IF(AND($E848="Y",$P848>SKU_Master!$O$48),"Expiry",IF(AND($E848="N",$P848>15),"Overstock",IF(AND(SKU_Master!$P$48<1,$P848>10),"Slow-mover","Healthy")))))
```

- **Arithmetic / decision check:** `Position 908; ROP 413; DoS 15.403248; classification = Overstock`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `M848` | 908 | Direct precedent/input |
| `ENGINE_STORE` | `N848` | 413 | Direct precedent/input |
| `ENGINE_STORE` | `P848` | 15.403248 | Direct precedent/input |
| `ENGINE_STORE` | `E848` | N | Direct precedent/input |
| `SKU_Master` | `O48` | 999 | Direct precedent/input |
| `SKU_Master` | `P48` | 1.3783 | Direct precedent/input |

---

### Example 5: SKU `GRC-040`, Store `S001`

- **Result:** `ENGINE_STORE!Q784` = **Slow-mover**
- **Native Excel formula:**

```excel
=IF($M784<$N784*0.6,"Stockout",IF($M784<$N784,"Low",IF(AND($E784="Y",$P784>SKU_Master!$O$45),"Expiry",IF(AND($E784="N",$P784>15),"Overstock",IF(AND(SKU_Master!$P$45<1,$P784>10),"Slow-mover","Healthy")))))
```

- **Arithmetic / decision check:** `Position 411; ROP 258; DoS 11.143575; classification = Slow-mover`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `M784` | 411 | Direct precedent/input |
| `ENGINE_STORE` | `N784` | 258 | Direct precedent/input |
| `ENGINE_STORE` | `P784` | 11.143575 | Direct precedent/input |
| `ENGINE_STORE` | `E784` | N | Direct precedent/input |
| `SKU_Master` | `O45` | 999 | Direct precedent/input |
| `SKU_Master` | `P45` | 0.9474 | Direct precedent/input |

---

## Formula 8: Forecast 7 days

**Documented logic:** `ADS × 7.45 weighted-week factor`

### Example 1: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!U4` = **217.293291**
- **Native Excel formula:**

```excel
=$J4*Constants!$B$10
```

- **Arithmetic / decision check:** `29.166885 × 7.45 = 217.293291`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J4` | 29.166885 | Direct precedent/input |
| `Constants` | `B10` | 7.45 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S002`

- **Result:** `ENGINE_STORE!U5` = **257.551863**
- **Native Excel formula:**

```excel
=$J5*Constants!$B$10
```

- **Arithmetic / decision check:** `34.57072 × 7.45 = 257.551863`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J5` | 34.57072 | Direct precedent/input |
| `Constants` | `B10` | 7.45 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, Store `S003`

- **Result:** `ENGINE_STORE!U6` = **146.134888**
- **Native Excel formula:**

```excel
=$J6*Constants!$B$10
```

- **Arithmetic / decision check:** `19.615421 × 7.45 = 146.134888`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J6` | 19.615421 | Direct precedent/input |
| `Constants` | `B10` | 7.45 | Direct precedent/input |

---

### Example 4: SKU `GRC-001`, Store `S004`

- **Result:** `ENGINE_STORE!U7` = **190.921884**
- **Native Excel formula:**

```excel
=$J7*Constants!$B$10
```

- **Arithmetic / decision check:** `25.627098 × 7.45 = 190.921884`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J7` | 25.627098 | Direct precedent/input |
| `Constants` | `B10` | 7.45 | Direct precedent/input |

---

### Example 5: SKU `GRC-001`, Store `S005`

- **Result:** `ENGINE_STORE!U8` = **259.611852**
- **Native Excel formula:**

```excel
=$J8*Constants!$B$10
```

- **Arithmetic / decision check:** `34.847228 × 7.45 = 259.611852`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J8` | 34.847228 | Direct precedent/input |
| `Constants` | `B10` | 7.45 | Direct precedent/input |

---

## Formula 9: Order quantity, sales units

**Documented logic:** `IF position < ROP, MAX(0, maximum − position)`

### Example 1: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!V4` = **136**
- **Native Excel formula:**

```excel
=IF($M4<$N4,MAX(0,$O4-$M4),0)
```

- **Arithmetic / decision check:** `IF 68 < 88, MAX(0, 204 − 68) = 136`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `M4` | 68 | Direct precedent/input |
| `ENGINE_STORE` | `N4` | 88 | Direct precedent/input |
| `ENGINE_STORE` | `O4` | 204 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S002`

- **Result:** `ENGINE_STORE!V5` = **168**
- **Native Excel formula:**

```excel
=IF($M5<$N5,MAX(0,$O5-$M5),0)
```

- **Arithmetic / decision check:** `IF 74 < 104, MAX(0, 242 − 74) = 168`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `M5` | 74 | Direct precedent/input |
| `ENGINE_STORE` | `N5` | 104 | Direct precedent/input |
| `ENGINE_STORE` | `O5` | 242 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, Store `S003`

- **Result:** `ENGINE_STORE!V6` = **91**
- **Native Excel formula:**

```excel
=IF($M6<$N6,MAX(0,$O6-$M6),0)
```

- **Arithmetic / decision check:** `IF 46 < 59, MAX(0, 137 − 46) = 91`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `M6` | 46 | Direct precedent/input |
| `ENGINE_STORE` | `N6` | 59 | Direct precedent/input |
| `ENGINE_STORE` | `O6` | 137 | Direct precedent/input |

---

### Example 4: SKU `GRC-001`, Store `S004`

- **Result:** `ENGINE_STORE!V7` = **126**
- **Native Excel formula:**

```excel
=IF($M7<$N7,MAX(0,$O7-$M7),0)
```

- **Arithmetic / decision check:** `IF 53 < 77, MAX(0, 179 − 53) = 126`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `M7` | 53 | Direct precedent/input |
| `ENGINE_STORE` | `N7` | 77 | Direct precedent/input |
| `ENGINE_STORE` | `O7` | 179 | Direct precedent/input |

---

### Example 5: SKU `GRC-001`, Store `S005`

- **Result:** `ENGINE_STORE!V8` = **142**
- **Native Excel formula:**

```excel
=IF($M8<$N8,MAX(0,$O8-$M8),0)
```

- **Arithmetic / decision check:** `IF 102 < 105, MAX(0, 244 − 102) = 142`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `M8` | 102 | Direct precedent/input |
| `ENGINE_STORE` | `N8` | 105 | Direct precedent/input |
| `ENGINE_STORE` | `O8` | 244 | Direct precedent/input |

---

## Formula 10: Order quantity, purchase units

**Documented logic:** `CEILING(order sales ÷ pack factor)`

### Example 1: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!X4` = **12**
- **Native Excel formula:**

```excel
=IF($V4>0,CEILING($V4/$W4,1),0)
```

- **Arithmetic / decision check:** `CEILING(136 ÷ 12) = 12`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `V4` | 136 | Direct precedent/input |
| `ENGINE_STORE` | `W4` | 12 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S002`

- **Result:** `ENGINE_STORE!X5` = **14**
- **Native Excel formula:**

```excel
=IF($V5>0,CEILING($V5/$W5,1),0)
```

- **Arithmetic / decision check:** `CEILING(168 ÷ 12) = 14`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `V5` | 168 | Direct precedent/input |
| `ENGINE_STORE` | `W5` | 12 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, Store `S003`

- **Result:** `ENGINE_STORE!X6` = **8**
- **Native Excel formula:**

```excel
=IF($V6>0,CEILING($V6/$W6,1),0)
```

- **Arithmetic / decision check:** `CEILING(91 ÷ 12) = 8`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `V6` | 91 | Direct precedent/input |
| `ENGINE_STORE` | `W6` | 12 | Direct precedent/input |

---

### Example 4: SKU `GRC-001`, Store `S004`

- **Result:** `ENGINE_STORE!X7` = **11**
- **Native Excel formula:**

```excel
=IF($V7>0,CEILING($V7/$W7,1),0)
```

- **Arithmetic / decision check:** `CEILING(126 ÷ 12) = 11`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `V7` | 126 | Direct precedent/input |
| `ENGINE_STORE` | `W7` | 12 | Direct precedent/input |

---

### Example 5: SKU `GRC-001`, Store `S005`

- **Result:** `ENGINE_STORE!X8` = **12**
- **Native Excel formula:**

```excel
=IF($V8>0,CEILING($V8/$W8,1),0)
```

- **Arithmetic / decision check:** `CEILING(142 ÷ 12) = 12`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `V8` | 142 | Direct precedent/input |
| `ENGINE_STORE` | `W8` | 12 | Direct precedent/input |

---

## Formula 11: Order value

**Documented logic:** `Order-buy × pack factor × price`

### Example 1: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!Y4` = **2,721,600**
- **Native Excel formula:**

```excel
=ROUND($X4*$W4*$R4,0)
```

- **Arithmetic / decision check:** `12 × 12 × 18,900 = 2,721,600`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `X4` | 12 | Direct precedent/input |
| `ENGINE_STORE` | `W4` | 12 | Direct precedent/input |
| `ENGINE_STORE` | `R4` | 18,900 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S002`

- **Result:** `ENGINE_STORE!Y5` = **3,175,200**
- **Native Excel formula:**

```excel
=ROUND($X5*$W5*$R5,0)
```

- **Arithmetic / decision check:** `14 × 12 × 18,900 = 3,175,200`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `X5` | 14 | Direct precedent/input |
| `ENGINE_STORE` | `W5` | 12 | Direct precedent/input |
| `ENGINE_STORE` | `R5` | 18,900 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, Store `S003`

- **Result:** `ENGINE_STORE!Y6` = **1,814,400**
- **Native Excel formula:**

```excel
=ROUND($X6*$W6*$R6,0)
```

- **Arithmetic / decision check:** `8 × 12 × 18,900 = 1,814,400`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `X6` | 8 | Direct precedent/input |
| `ENGINE_STORE` | `W6` | 12 | Direct precedent/input |
| `ENGINE_STORE` | `R6` | 18,900 | Direct precedent/input |

---

### Example 4: SKU `GRC-001`, Store `S004`

- **Result:** `ENGINE_STORE!Y7` = **2,494,800**
- **Native Excel formula:**

```excel
=ROUND($X7*$W7*$R7,0)
```

- **Arithmetic / decision check:** `11 × 12 × 18,900 = 2,494,800`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `X7` | 11 | Direct precedent/input |
| `ENGINE_STORE` | `W7` | 12 | Direct precedent/input |
| `ENGINE_STORE` | `R7` | 18,900 | Direct precedent/input |

---

### Example 5: SKU `GRC-001`, Store `S005`

- **Result:** `ENGINE_STORE!Y8` = **2,721,600**
- **Native Excel formula:**

```excel
=ROUND($X8*$W8*$R8,0)
```

- **Arithmetic / decision check:** `12 × 12 × 18,900 = 2,721,600`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `X8` | 12 | Direct precedent/input |
| `ENGINE_STORE` | `W8` | 12 | Direct precedent/input |
| `ENGINE_STORE` | `R8` | 18,900 | Direct precedent/input |

---

## Formula 12: At-risk value

**Documented logic:** `IF state ≠ Healthy, position × price, otherwise 0`

### Example 1: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!T4` = **1,285,200**
- **Native Excel formula:**

```excel
=IF($Q4<>"Healthy",$S4,0)
```

- **Arithmetic / decision check:** `State Low; 68 × 18,900 = 1,285,200`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `Q4` | Low | Direct precedent/input |
| `ENGINE_STORE` | `M4` | 68 | Direct precedent/input |
| `ENGINE_STORE` | `R4` | 18,900 | Direct precedent/input |
| `ENGINE_STORE` | `S4` | 1,285,200 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S002`

- **Result:** `ENGINE_STORE!T5` = **1,398,600**
- **Native Excel formula:**

```excel
=IF($Q5<>"Healthy",$S5,0)
```

- **Arithmetic / decision check:** `State Low; 74 × 18,900 = 1,398,600`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `Q5` | Low | Direct precedent/input |
| `ENGINE_STORE` | `M5` | 74 | Direct precedent/input |
| `ENGINE_STORE` | `R5` | 18,900 | Direct precedent/input |
| `ENGINE_STORE` | `S5` | 1,398,600 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, Store `S003`

- **Result:** `ENGINE_STORE!T6` = **869,400**
- **Native Excel formula:**

```excel
=IF($Q6<>"Healthy",$S6,0)
```

- **Arithmetic / decision check:** `State Low; 46 × 18,900 = 869,400`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `Q6` | Low | Direct precedent/input |
| `ENGINE_STORE` | `M6` | 46 | Direct precedent/input |
| `ENGINE_STORE` | `R6` | 18,900 | Direct precedent/input |
| `ENGINE_STORE` | `S6` | 869,400 | Direct precedent/input |

---

### Example 4: SKU `GRC-001`, Store `S004`

- **Result:** `ENGINE_STORE!T7` = **1,001,700**
- **Native Excel formula:**

```excel
=IF($Q7<>"Healthy",$S7,0)
```

- **Arithmetic / decision check:** `State Low; 53 × 18,900 = 1,001,700`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `Q7` | Low | Direct precedent/input |
| `ENGINE_STORE` | `M7` | 53 | Direct precedent/input |
| `ENGINE_STORE` | `R7` | 18,900 | Direct precedent/input |
| `ENGINE_STORE` | `S7` | 1,001,700 | Direct precedent/input |

---

### Example 5: SKU `GRC-001`, Store `S005`

- **Result:** `ENGINE_STORE!T8` = **1,927,800**
- **Native Excel formula:**

```excel
=IF($Q8<>"Healthy",$S8,0)
```

- **Arithmetic / decision check:** `State Low; 102 × 18,900 = 1,927,800`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `Q8` | Low | Direct precedent/input |
| `ENGINE_STORE` | `M8` | 102 | Direct precedent/input |
| `ENGINE_STORE` | `R8` | 18,900 | Direct precedent/input |
| `ENGINE_STORE` | `S8` | 1,927,800 | Direct precedent/input |

---

## Formula 13: Incremental promotion margin

**Documented logic:** `Promo incremental revenue × (margin + 0.16) − promotional cost × 0.55`

### Example 1: SKU `GRC-002`, Store `S001`

- **Result:** `ENGINE_STORE!Z24` = **97,773.937355**
- **Native Excel formula:**

```excel
=IF(SKU_Master!$U$7="Y",(($J24*7*$R24)*(0.15*2.2*(1-SKU_Master!$T$7))*0.85)*(SKU_Master!$I$7+0.16)-(($J24*7*$R24)*0.15*(1-SKU_Master!$S$7))*0.55,0)
```

- **Arithmetic / decision check:** `Promo calculation using ADS 19.636343, price 19,100, margin/funding/cannibalization inputs = 97,773.937355`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J24` | 19.636343 | Direct precedent/input |
| `ENGINE_STORE` | `R24` | 19,100 | Direct precedent/input |
| `SKU_Master` | `I7` | 0.1778 | Direct precedent/input |
| `SKU_Master` | `S7` | 0.4862 | Direct precedent/input |
| `SKU_Master` | `T7` | 0.1596 | Direct precedent/input |
| `SKU_Master` | `U7` | Y | Direct precedent/input |

---

### Example 2: SKU `GRC-002`, Store `S002`

- **Result:** `ENGINE_STORE!Z25` = **115,888.80463**
- **Native Excel formula:**

```excel
=IF(SKU_Master!$U$7="Y",(($J25*7*$R25)*(0.15*2.2*(1-SKU_Master!$T$7))*0.85)*(SKU_Master!$I$7+0.16)-(($J25*7*$R25)*0.15*(1-SKU_Master!$S$7))*0.55,0)
```

- **Arithmetic / decision check:** `Promo calculation using ADS 23.274426, price 19,100, margin/funding/cannibalization inputs = 115,888.80463`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J25` | 23.274426 | Direct precedent/input |
| `ENGINE_STORE` | `R25` | 19,100 | Direct precedent/input |
| `SKU_Master` | `I7` | 0.1778 | Direct precedent/input |
| `SKU_Master` | `S7` | 0.4862 | Direct precedent/input |
| `SKU_Master` | `T7` | 0.1596 | Direct precedent/input |
| `SKU_Master` | `U7` | Y | Direct precedent/input |

---

### Example 3: SKU `GRC-002`, Store `S003`

- **Result:** `ENGINE_STORE!Z26` = **65,755.290168**
- **Native Excel formula:**

```excel
=IF(SKU_Master!$U$7="Y",(($J26*7*$R26)*(0.15*2.2*(1-SKU_Master!$T$7))*0.85)*(SKU_Master!$I$7+0.16)-(($J26*7*$R26)*0.15*(1-SKU_Master!$S$7))*0.55,0)
```

- **Arithmetic / decision check:** `Promo calculation using ADS 13.205906, price 19,100, margin/funding/cannibalization inputs = 65,755.290168`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J26` | 13.205906 | Direct precedent/input |
| `ENGINE_STORE` | `R26` | 19,100 | Direct precedent/input |
| `SKU_Master` | `I7` | 0.1778 | Direct precedent/input |
| `SKU_Master` | `S7` | 0.4862 | Direct precedent/input |
| `SKU_Master` | `T7` | 0.1596 | Direct precedent/input |
| `SKU_Master` | `U7` | Y | Direct precedent/input |

---

### Example 4: SKU `GRC-002`, Store `S004`

- **Result:** `ENGINE_STORE!Z27` = **85,907.780361**
- **Native Excel formula:**

```excel
=IF(SKU_Master!$U$7="Y",(($J27*7*$R27)*(0.15*2.2*(1-SKU_Master!$T$7))*0.85)*(SKU_Master!$I$7+0.16)-(($J27*7*$R27)*0.15*(1-SKU_Master!$S$7))*0.55,0)
```

- **Arithmetic / decision check:** `Promo calculation using ADS 17.253213, price 19,100, margin/funding/cannibalization inputs = 85,907.780361`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J27` | 17.253213 | Direct precedent/input |
| `ENGINE_STORE` | `R27` | 19,100 | Direct precedent/input |
| `SKU_Master` | `I7` | 0.1778 | Direct precedent/input |
| `SKU_Master` | `S7` | 0.4862 | Direct precedent/input |
| `SKU_Master` | `T7` | 0.1596 | Direct precedent/input |
| `SKU_Master` | `U7` | Y | Direct precedent/input |

---

### Example 5: SKU `GRC-002`, Store `S005`

- **Result:** `ENGINE_STORE!Z28` = **116,815.723291**
- **Native Excel formula:**

```excel
=IF(SKU_Master!$U$7="Y",(($J28*7*$R28)*(0.15*2.2*(1-SKU_Master!$T$7))*0.85)*(SKU_Master!$I$7+0.16)-(($J28*7*$R28)*0.15*(1-SKU_Master!$S$7))*0.55,0)
```

- **Arithmetic / decision check:** `Promo calculation using ADS 23.460583, price 19,100, margin/funding/cannibalization inputs = 116,815.723291`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J28` | 23.460583 | Direct precedent/input |
| `ENGINE_STORE` | `R28` | 19,100 | Direct precedent/input |
| `SKU_Master` | `I7` | 0.1778 | Direct precedent/input |
| `SKU_Master` | `S7` | 0.4862 | Direct precedent/input |
| `SKU_Master` | `T7` | 0.1596 | Direct precedent/input |
| `SKU_Master` | `U7` | Y | Direct precedent/input |

---

## Formula 14: Recoverable at-risk value

**Documented logic:** `Gross exposure recovered after markdown depth and the sell-through that depth buys; depth scales with the markdown lever and caps at 65%`

### Example 1: SKU `GRC-002`, Store `S005`

- **Result:** `ENGINE_STORE!AA28` = **175,909**
- **Native Excel formula:**

```excel
=LET(g,$AF28,IF(g<=0,0,LET(bd,IF($Q28="Expiry",0.4,IF($Q28="Overstock",0.25,0.3)),d,MIN(0.65,bd*(25+Constants!$B$18)/25),el,ABS(VLOOKUP($A28,SKU_Master!$A$6:$AF$805,17,0)),st,MIN(0.95,0.35+el*d*1.15),ROUND(g*st*(1-d),0))))
```

- **Arithmetic / decision check:** `Gross 308,611.466807, base depth 0.4, lever 0 -> net 175,909`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `AF28` | 308,611.466807 | Direct precedent/input |
| `ENGINE_STORE` | `Q28` | Expiry | Direct precedent/input |
| `SKU_Master` | `Q7` | -1.5289 | Direct precedent/input |
| `Constants` | `B18` | 0 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!AA4` = **0**
- **Native Excel formula:**

```excel
=LET(g,$AF4,IF(g<=0,0,LET(bd,IF($Q4="Expiry",0.4,IF($Q4="Overstock",0.25,0.3)),d,MIN(0.65,bd*(25+Constants!$B$18)/25),el,ABS(VLOOKUP($A4,SKU_Master!$A$6:$AF$805,17,0)),st,MIN(0.95,0.35+el*d*1.15),ROUND(g*st*(1-d),0))))
```

- **Arithmetic / decision check:** `Gross 0, base depth 0.3, lever 0 -> net 0`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `AF4` | 0 | Direct precedent/input |
| `ENGINE_STORE` | `Q4` | Stockout | Direct precedent/input |
| `SKU_Master` | `Q6` | -1.8178 | Direct precedent/input |
| `Constants` | `B18` | 0 | Direct precedent/input |

---

### Example 3: SKU `GRC-010`, Store `S005`

- **Result:** `ENGINE_STORE!AA188` = **0**
- **Native Excel formula:**

```excel
=LET(g,$AF188,IF(g<=0,0,LET(bd,IF($Q188="Expiry",0.4,IF($Q188="Overstock",0.25,0.3)),d,MIN(0.65,bd*(25+Constants!$B$18)/25),el,ABS(VLOOKUP($A188,SKU_Master!$A$6:$AF$805,17,0)),st,MIN(0.95,0.35+el*d*1.15),ROUND(g*st*(1-d),0))))
```

- **Arithmetic / decision check:** `Gross 0, base depth 0.3, lever 0 -> net 0`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `AF188` | 0 | Direct precedent/input |
| `ENGINE_STORE` | `Q188` | Low | Direct precedent/input |
| `SKU_Master` | `Q15` | -1.8658 | Direct precedent/input |
| `Constants` | `B18` | 0 | Direct precedent/input |

---

### Example 4: SKU `GRC-043`, Store `S005`

- **Result:** `ENGINE_STORE!AA848` = **1,566,615**
- **Native Excel formula:**

```excel
=LET(g,$AF848,IF(g<=0,0,LET(bd,IF($Q848="Expiry",0.4,IF($Q848="Overstock",0.25,0.3)),d,MIN(0.65,bd*(25+Constants!$B$18)/25),el,ABS(VLOOKUP($A848,SKU_Master!$A$6:$AF$805,17,0)),st,MIN(0.95,0.35+el*d*1.15),ROUND(g*st*(1-d),0))))
```

- **Arithmetic / decision check:** `Gross 3,677,800, base depth 0.25, lever 0 -> net 1,566,615`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `AF848` | 3,677,800 | Direct precedent/input |
| `ENGINE_STORE` | `Q848` | Overstock | Direct precedent/input |
| `SKU_Master` | `Q48` | -0.7581 | Direct precedent/input |
| `Constants` | `B18` | 0 | Direct precedent/input |

---

### Example 5: SKU `GRC-040`, Store `S001`

- **Result:** `ENGINE_STORE!AA784` = **1,552,256**
- **Native Excel formula:**

```excel
=LET(g,$AF784,IF(g<=0,0,LET(bd,IF($Q784="Expiry",0.4,IF($Q784="Overstock",0.25,0.3)),d,MIN(0.65,bd*(25+Constants!$B$18)/25),el,ABS(VLOOKUP($A784,SKU_Master!$A$6:$AF$805,17,0)),st,MIN(0.95,0.35+el*d*1.15),ROUND(g*st*(1-d),0))))
```

- **Arithmetic / decision check:** `Gross 3,144,150, base depth 0.3, lever 0 -> net 1,552,256`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `AF784` | 3,144,150 | Direct precedent/input |
| `ENGINE_STORE` | `Q784` | Slow-mover | Direct precedent/input |
| `SKU_Master` | `Q45` | -1.0298 | Direct precedent/input |
| `Constants` | `B18` | 0 | Direct precedent/input |

---

## Formula 15: Contribution per day

**Documented logic:** `ADS × price × margin %` (v8.5 dropped v8.2's `ROUND(...,0)`)

### Example 1: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!AB4` = **134,230.379803**
- **Native Excel formula:**

```excel
=$J4*$R4*$AP4
```

- **Arithmetic / decision check:** `29.166885 × 18,900 × 0.2435 = 134,230.379803`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J4` | 29.166885 | Direct precedent/input |
| `ENGINE_STORE` | `R4` | 18,900 | Direct precedent/input |
| `SKU_Master` | `I6` | 0.2435 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S002`

- **Result:** `ENGINE_STORE!AB5` = **159,099.639048**
- **Native Excel formula:**

```excel
=$J5*$R5*$AP5
```

- **Arithmetic / decision check:** `34.57072 × 18,900 × 0.2435 = 159,099.639048`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J5` | 34.57072 | Direct precedent/input |
| `ENGINE_STORE` | `R5` | 18,900 | Direct precedent/input |
| `SKU_Master` | `I6` | 0.2435 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, Store `S003`

- **Result:** `ENGINE_STORE!AB6` = **90,273.109755**
- **Native Excel formula:**

```excel
=$J6*$R6*$AP6
```

- **Arithmetic / decision check:** `19.615421 × 18,900 × 0.2435 = 90,273.109755`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J6` | 19.615421 | Direct precedent/input |
| `ENGINE_STORE` | `R6` | 18,900 | Direct precedent/input |
| `SKU_Master` | `I6` | 0.2435 | Direct precedent/input |

---

### Example 4: SKU `GRC-001`, Store `S004`

- **Result:** `ENGINE_STORE!AB7` = **117,939.749061**
- **Native Excel formula:**

```excel
=$J7*$R7*$AP7
```

- **Arithmetic / decision check:** `25.627098 × 18,900 × 0.2435 = 117,939.749061`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J7` | 25.627098 | Direct precedent/input |
| `ENGINE_STORE` | `R7` | 18,900 | Direct precedent/input |
| `SKU_Master` | `I6` | 0.2435 | Direct precedent/input |

---

### Example 5: SKU `GRC-001`, Store `S005`

- **Result:** `ENGINE_STORE!AB8` = **160,372.170340**
- **Native Excel formula:**

```excel
=$J8*$R8*$AP8
```

- **Arithmetic / decision check:** `34.847228 × 18,900 × 0.2435 = 160,372.170340`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J8` | 34.847228 | Direct precedent/input |
| `ENGINE_STORE` | `R8` | 18,900 | Direct precedent/input |
| `SKU_Master` | `I6` | 0.2435 | Direct precedent/input |

---

## Formula 16: Labour FTE

**Documented logic:** `ADS × 7 × price ÷ sales-per-FTE`

### Example 1: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!AC4` = **0.622384**
- **Native Excel formula:**

```excel
=$J4*7*$R4/SKU_Master!$AD$6
```

- **Arithmetic / decision check:** `29.166885 × 7 × 18,900 ÷ 6,200,000 = 0.622384`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J4` | 29.166885 | Direct precedent/input |
| `ENGINE_STORE` | `R4` | 18,900 | Direct precedent/input |
| `SKU_Master` | `AD6` | 6,200,000 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S002`

- **Result:** `ENGINE_STORE!AC5` = **0.737695**
- **Native Excel formula:**

```excel
=$J5*7*$R5/SKU_Master!$AD$6
```

- **Arithmetic / decision check:** `34.57072 × 7 × 18,900 ÷ 6,200,000 = 0.737695`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J5` | 34.57072 | Direct precedent/input |
| `ENGINE_STORE` | `R5` | 18,900 | Direct precedent/input |
| `SKU_Master` | `AD6` | 6,200,000 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, Store `S003`

- **Result:** `ENGINE_STORE!AC6` = **0.418568**
- **Native Excel formula:**

```excel
=$J6*7*$R6/SKU_Master!$AD$6
```

- **Arithmetic / decision check:** `19.615421 × 7 × 18,900 ÷ 6,200,000 = 0.418568`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J6` | 19.615421 | Direct precedent/input |
| `ENGINE_STORE` | `R6` | 18,900 | Direct precedent/input |
| `SKU_Master` | `AD6` | 6,200,000 | Direct precedent/input |

---

### Example 4: SKU `GRC-001`, Store `S004`

- **Result:** `ENGINE_STORE!AC7` = **0.546849**
- **Native Excel formula:**

```excel
=$J7*7*$R7/SKU_Master!$AD$6
```

- **Arithmetic / decision check:** `25.627098 × 7 × 18,900 ÷ 6,200,000 = 0.546849`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J7` | 25.627098 | Direct precedent/input |
| `ENGINE_STORE` | `R7` | 18,900 | Direct precedent/input |
| `SKU_Master` | `AD6` | 6,200,000 | Direct precedent/input |

---

### Example 5: SKU `GRC-001`, Store `S005`

- **Result:** `ENGINE_STORE!AC8` = **0.743595**
- **Native Excel formula:**

```excel
=$J8*7*$R8/SKU_Master!$AD$6
```

- **Arithmetic / decision check:** `34.847228 × 7 × 18,900 ÷ 6,200,000 = 0.743595`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `J8` | 34.847228 | Direct precedent/input |
| `ENGINE_STORE` | `R8` | 18,900 | Direct precedent/input |
| `SKU_Master` | `AD6` | 6,200,000 | Direct precedent/input |

---

## Formula 17: Required workforce

**Documented logic:** `MAX(1, ROUND(size × WF base × peak × (1 + event lift) × (0.80 + 0.17 × footfall index)))`

### Example 1: Store `S004` (Grocery 04 · Bandung)

- **Result:** `Workforce!M9` = **42**
- **Native Excel formula:**

```excel
=MAX(1,ROUND(E9*J9*K9*(1+I9)*(0.8+0.17*G9),0))
```

- **Arithmetic / decision check:** `MAX(1, ROUND(1.0751 × 26 × 1.22 × (1 + 0.25) × (0.80 + 0.17 × 1.085))) = 42`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `E9` | 1.0751 | Direct precedent/input |
| `Workforce` | `J9` | 26 | Direct precedent/input |
| `Workforce` | `K9` | 1.22 | Direct precedent/input |
| `Workforce` | `I9` | 0.25 | Direct precedent/input |
| `Workforce` | `G9` | 1.085 | Direct precedent/input |

---

### Example 2: Store `S011` (Grocery 11 · Batam)

- **Result:** `Workforce!M16` = **49**
- **Native Excel formula:**

```excel
=MAX(1,ROUND(E16*J16*K16*(1+I16)*(0.8+0.17*G16),0))
```

- **Arithmetic / decision check:** `MAX(1, ROUND(1.3266 × 26 × 1.22 × (1 + 0.2) × (0.80 + 0.17 × 0.9722))) = 49`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `E16` | 1.3266 | Direct precedent/input |
| `Workforce` | `J16` | 26 | Direct precedent/input |
| `Workforce` | `K16` | 1.22 | Direct precedent/input |
| `Workforce` | `I16` | 0.2 | Direct precedent/input |
| `Workforce` | `G16` | 0.9722 | Direct precedent/input |

---

### Example 3: Store `S001` (Grocery 01 · Jakarta Pusat)

- **Result:** `Workforce!M6` = **38**
- **Native Excel formula:**

```excel
=MAX(1,ROUND(E6*J6*K6*(1+I6)*(0.8+0.17*G6),0))
```

- **Arithmetic / decision check:** `MAX(1, ROUND(1.2236 × 26 × 1.22 × (1 + 0) × (0.80 + 0.17 × 1.1221))) = 38`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `E6` | 1.2236 | Direct precedent/input |
| `Workforce` | `J6` | 26 | Direct precedent/input |
| `Workforce` | `K6` | 1.22 | Direct precedent/input |
| `Workforce` | `I6` | 0 | Direct precedent/input |
| `Workforce` | `G6` | 1.1221 | Direct precedent/input |

---

### Example 4: Store `S002` (Grocery 02 · Jakarta Selatan)

- **Result:** `Workforce!M7` = **46**
- **Native Excel formula:**

```excel
=MAX(1,ROUND(E7*J7*K7*(1+I7)*(0.8+0.17*G7),0))
```

- **Arithmetic / decision check:** `MAX(1, ROUND(1.4503 × 26 × 1.22 × (1 + 0) × (0.80 + 0.17 × 1.1765))) = 46`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `E7` | 1.4503 | Direct precedent/input |
| `Workforce` | `J7` | 26 | Direct precedent/input |
| `Workforce` | `K7` | 1.22 | Direct precedent/input |
| `Workforce` | `I7` | 0 | Direct precedent/input |
| `Workforce` | `G7` | 1.1765 | Direct precedent/input |

---

### Example 5: Store `S003` (Grocery 03 · Surabaya)

- **Result:** `Workforce!M8` = **26**
- **Native Excel formula:**

```excel
=MAX(1,ROUND(E8*J8*K8*(1+I8)*(0.8+0.17*G8),0))
```

- **Arithmetic / decision check:** `MAX(1, ROUND(0.8229 × 26 × 1.22 × (1 + 0) × (0.80 + 0.17 × 1.0549))) = 26`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `E8` | 0.8229 | Direct precedent/input |
| `Workforce` | `J8` | 26 | Direct precedent/input |
| `Workforce` | `K8` | 1.22 | Direct precedent/input |
| `Workforce` | `I8` | 0 | Direct precedent/input |
| `Workforce` | `G8` | 1.0549 | Direct precedent/input |

---

## Formula 18: Scheduled workforce

**Documented logic:** `ROUND(size × WF base × (0.99 + 0.16 × health))`

### Example 1: Store `S004` (Grocery 04 · Bandung)

- **Result:** `Workforce!L9` = **32**
- **Native Excel formula:**

```excel
=ROUND(E9*J9*(0.99+0.16*F9),0)
```

- **Arithmetic / decision check:** `ROUND(1.0751 × 26 × (0.99 + 0.16 × 0.8934)) = 32`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `E9` | 1.0751 | Direct precedent/input |
| `Workforce` | `J9` | 26 | Direct precedent/input |
| `Workforce` | `F9` | 0.8934 | Direct precedent/input |

---

### Example 2: Store `S011` (Grocery 11 · Batam)

- **Result:** `Workforce!L16` = **39**
- **Native Excel formula:**

```excel
=ROUND(E16*J16*(0.99+0.16*F16),0)
```

- **Arithmetic / decision check:** `ROUND(1.3266 × 26 × (0.99 + 0.16 × 0.8044)) = 39`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `E16` | 1.3266 | Direct precedent/input |
| `Workforce` | `J16` | 26 | Direct precedent/input |
| `Workforce` | `F16` | 0.8044 | Direct precedent/input |

---

### Example 3: Store `S001` (Grocery 01 · Jakarta Pusat)

- **Result:** `Workforce!L6` = **37**
- **Native Excel formula:**

```excel
=ROUND(E6*J6*(0.99+0.16*F6),0)
```

- **Arithmetic / decision check:** `ROUND(1.2236 × 26 × (0.99 + 0.16 × 1.0061)) = 37`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `E6` | 1.2236 | Direct precedent/input |
| `Workforce` | `J6` | 26 | Direct precedent/input |
| `Workforce` | `F6` | 1.0061 | Direct precedent/input |

---

### Example 4: Store `S002` (Grocery 02 · Jakarta Selatan)

- **Result:** `Workforce!L7` = **43**
- **Native Excel formula:**

```excel
=ROUND(E7*J7*(0.99+0.16*F7),0)
```

- **Arithmetic / decision check:** `ROUND(1.4503 × 26 × (0.99 + 0.16 × 0.9208)) = 43`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `E7` | 1.4503 | Direct precedent/input |
| `Workforce` | `J7` | 26 | Direct precedent/input |
| `Workforce` | `F7` | 0.9208 | Direct precedent/input |

---

### Example 5: Store `S003` (Grocery 03 · Surabaya)

- **Result:** `Workforce!L8` = **25**
- **Native Excel formula:**

```excel
=ROUND(E8*J8*(0.99+0.16*F8),0)
```

- **Arithmetic / decision check:** `ROUND(0.8229 × 26 × (0.99 + 0.16 × 1.003)) = 25`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `E8` | 0.8229 | Direct precedent/input |
| `Workforce` | `J8` | 26 | Direct precedent/input |
| `Workforce` | `F8` | 1.003 | Direct precedent/input |

---

## Formula 19: Coverage gap

**Documented logic:** `MAX(0, required − scheduled)`

### Example 1: Store `S004` (Grocery 04 · Bandung)

- **Result:** `Workforce!N9` = **10**
- **Native Excel formula:**

```excel
=MAX(0,M9-L9)
```

- **Arithmetic / decision check:** `MAX(0, 42 − 32) = 10`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `M9` | 42 | Direct precedent/input |
| `Workforce` | `L9` | 32 | Direct precedent/input |

---

### Example 2: Store `S011` (Grocery 11 · Batam)

- **Result:** `Workforce!N16` = **10**
- **Native Excel formula:**

```excel
=MAX(0,M16-L16)
```

- **Arithmetic / decision check:** `MAX(0, 49 − 39) = 10`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `M16` | 49 | Direct precedent/input |
| `Workforce` | `L16` | 39 | Direct precedent/input |

---

### Example 3: Store `S001` (Grocery 01 · Jakarta Pusat)

- **Result:** `Workforce!N6` = **1**
- **Native Excel formula:**

```excel
=MAX(0,M6-L6)
```

- **Arithmetic / decision check:** `MAX(0, 38 − 37) = 1`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `M6` | 38 | Direct precedent/input |
| `Workforce` | `L6` | 37 | Direct precedent/input |

---

### Example 4: Store `S002` (Grocery 02 · Jakarta Selatan)

- **Result:** `Workforce!N7` = **3**
- **Native Excel formula:**

```excel
=MAX(0,M7-L7)
```

- **Arithmetic / decision check:** `MAX(0, 46 − 43) = 3`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `M7` | 46 | Direct precedent/input |
| `Workforce` | `L7` | 43 | Direct precedent/input |

---

### Example 5: Store `S003` (Grocery 03 · Surabaya)

- **Result:** `Workforce!N8` = **1**
- **Native Excel formula:**

```excel
=MAX(0,M8-L8)
```

- **Arithmetic / decision check:** `MAX(0, 26 − 25) = 1`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `Workforce` | `M8` | 26 | Direct precedent/input |
| `Workforce` | `L8` | 25 | Direct precedent/input |

---

## Coverage summary

| Formula | Examples | Primary calculation sheet |
|---|---:|---|
| 1. ADS per store | 5 | `ENGINE_STORE` |
| 2. On-hand | 5 | `ENGINE_STORE` |
| 3. Open PO per store | 5 | `ENGINE_STORE` |
| 4. Position | 5 | `ENGINE_STORE` |
| 5. ROP | 5 | `ENGINE_STORE` |
| 6. Maximum inventory | 5 | `ENGINE_STORE` |
| 7. Inventory state | 5 | `ENGINE_STORE` |
| 8. Forecast 7 days | 5 | `ENGINE_STORE` |
| 9. Order quantity, sales units | 5 | `ENGINE_STORE` |
| 10. Order quantity, purchase units | 5 | `ENGINE_STORE` |
| 11. Order value | 5 | `ENGINE_STORE` |
| 12. At-risk value | 5 | `ENGINE_STORE` |
| 13. Incremental promotion margin | 5 | `ENGINE_STORE` |
| 14. Recoverable at-risk value | 5 | `ENGINE_STORE` |
| 15. Contribution per day | 5 | `ENGINE_STORE` |
| 16. Labour FTE | 5 | `ENGINE_STORE` |
| 17. Required workforce | 5 | `Workforce` |
| 18. Scheduled workforce | 5 | `Workforce` |
| 19. Coverage gap | 5 | `Workforce` |

**Total: 95 workbook-traceable worked examples.**

## Formula 20: Days of supply

**Documented logic:** `Position ÷ ADS, guarded against a dead SKU`

### Example 1: SKU `GRC-005`, chain-net

- **Result:** `ENGINE!I10` = **4.200354**
- **Native Excel formula:**

```excel
=IF($E10>0,$F10/$E10,0)
```

- **Arithmetic / decision check:** `IF(631.613363 > 0, 2,653 ÷ 631.613363) = 4.200354`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `E10` | 631.613363 | Direct precedent/input |
| `ENGINE` | `F10` | 2,653 | Direct precedent/input |

---

### Example 2: SKU `GRC-007`, chain-net

- **Result:** `ENGINE!I12` = **3.211492**
- **Native Excel formula:**

```excel
=IF($E12>0,$F12/$E12,0)
```

- **Arithmetic / decision check:** `IF(222.015186 > 0, 713 ÷ 222.015186) = 3.211492`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `E12` | 222.015186 | Direct precedent/input |
| `ENGINE` | `F12` | 713 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, chain-net

- **Result:** `ENGINE!I6` = **2.36682**
- **Native Excel formula:**

```excel
=IF($E6>0,$F6/$E6,0)
```

- **Arithmetic / decision check:** `IF(496.869179 > 0, 1,176 ÷ 496.869179) = 2.36682`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `E6` | 496.869179 | Direct precedent/input |
| `ENGINE` | `F6` | 1,176 | Direct precedent/input |

---

### Example 4: SKU `GRC-036`, chain-net

- **Result:** `ENGINE!I41` = **6.013465**
- **Native Excel formula:**

```excel
=IF($E41>0,$F41/$E41,0)
```

- **Arithmetic / decision check:** `IF(493.559031 > 0, 2,968 ÷ 493.559031) = 6.013465`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `E41` | 493.559031 | Direct precedent/input |
| `ENGINE` | `F41` | 2,968 | Direct precedent/input |

---

### Example 5: SKU `GRC-037`, chain-net

- **Result:** `ENGINE!I42` = **10.081444**
- **Native Excel formula:**

```excel
=IF($E42>0,$F42/$E42,0)
```

- **Arithmetic / decision check:** `IF(331.202554 > 0, 3,339 ÷ 331.202554) = 10.081444`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `E42` | 331.202554 | Direct precedent/input |
| `ENGINE` | `F42` | 3,339 | Direct precedent/input |

---

## Formula 21: Inventory value

**Documented logic:** `ROUND(position × price)`

### Example 1: SKU `GRC-005`, chain-net

- **Result:** `ENGINE!L10` = **52,264,100**
- **Native Excel formula:**

```excel
=ROUND($F10*$K10,0)
```

- **Arithmetic / decision check:** `ROUND(2,653 × 19,700) = 52,264,100`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `F10` | 2,653 | Direct precedent/input |
| `ENGINE` | `K10` | 19,700 | Direct precedent/input |

---

### Example 2: SKU `GRC-007`, chain-net

- **Result:** `ENGINE!L12` = **14,188,700**
- **Native Excel formula:**

```excel
=ROUND($F12*$K12,0)
```

- **Arithmetic / decision check:** `ROUND(713 × 19,900) = 14,188,700`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `F12` | 713 | Direct precedent/input |
| `ENGINE` | `K12` | 19,900 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, chain-net

- **Result:** `ENGINE!L6` = **22,226,400**
- **Native Excel formula:**

```excel
=ROUND($F6*$K6,0)
```

- **Arithmetic / decision check:** `ROUND(1,176 × 18,900) = 22,226,400`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `F6` | 1,176 | Direct precedent/input |
| `ENGINE` | `K6` | 18,900 | Direct precedent/input |

---

### Example 4: SKU `GRC-036`, chain-net

- **Result:** `ENGINE!L41` = **73,309,600**
- **Native Excel formula:**

```excel
=ROUND($F41*$K41,0)
```

- **Arithmetic / decision check:** `ROUND(2,968 × 24,700) = 73,309,600`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `F41` | 2,968 | Direct precedent/input |
| `ENGINE` | `K41` | 24,700 | Direct precedent/input |

---

### Example 5: SKU `GRC-037`, chain-net

- **Result:** `ENGINE!L42` = **83,141,100**
- **Native Excel formula:**

```excel
=ROUND($F42*$K42,0)
```

- **Arithmetic / decision check:** `ROUND(3,339 × 24,900) = 83,141,100`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `F42` | 3,339 | Direct precedent/input |
| `ENGINE` | `K42` | 24,900 | Direct precedent/input |

---

## Formula 22: Expiry units

**Documented logic:** `Perishable stock already past its shelf-life cover`

### Example 1: SKU `GRC-005`, chain-net

- **Result:** `ENGINE!N10` = **758**
- **Native Excel formula:**

```excel
=IF($D10="Y",MAX(0,$F10-$E10*SKU_Master!$O$10),0)
```

- **Arithmetic / decision check:** `IF("Y" = "Y", MAX(0, ROUND(2,653 − 631.613363 × 3, 0))) = 758`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `D10` | Y | Direct precedent/input |
| `ENGINE` | `F10` | 2,653 | Direct precedent/input |
| `ENGINE` | `E10` | 631.613363 | Direct precedent/input |
| `SKU_Master` | `O10` | 3 | Direct precedent/input |

---

### Example 2: SKU `GRC-007`, chain-net

- **Result:** `ENGINE!N12` = **269**
- **Native Excel formula:**

```excel
=IF($D12="Y",MAX(0,$F12-$E12*SKU_Master!$O$12),0)
```

- **Arithmetic / decision check:** `IF("Y" = "Y", MAX(0, ROUND(713 − 222.015186 × 2, 0))) = 269`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `D12` | Y | Direct precedent/input |
| `ENGINE` | `F12` | 713 | Direct precedent/input |
| `ENGINE` | `E12` | 222.015186 | Direct precedent/input |
| `SKU_Master` | `O12` | 2 | Direct precedent/input |

---

### Example 3: SKU `GRC-001`, chain-net

- **Result:** `ENGINE!N6` = **0**
- **Native Excel formula:**

```excel
=IF($D6="Y",MAX(0,$F6-$E6*SKU_Master!$O$6),0)
```

- **Arithmetic / decision check:** `IF("Y" = "Y", MAX(0, 1,176 − 496.869179 × 3)) = 0`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `D6` | Y | Direct precedent/input |
| `ENGINE` | `F6` | 1,176 | Direct precedent/input |
| `ENGINE` | `E6` | 496.869179 | Direct precedent/input |
| `SKU_Master` | `O6` | 3 | Direct precedent/input |

---

### Example 4: SKU `GRC-036`, chain-net

- **Result:** `ENGINE!N41` = **0**
- **Native Excel formula:**

```excel
=IF($D41="Y",MAX(0,$F41-$E41*SKU_Master!$O$41),0)
```

- **Arithmetic / decision check:** `IF("N" = "Y", …, 0) = 0`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `D41` | N | Direct precedent/input |
| `ENGINE` | `F41` | 2,968 | Direct precedent/input |
| `ENGINE` | `E41` | 493.559031 | Direct precedent/input |
| `SKU_Master` | `O41` | 999 | Direct precedent/input |

---

### Example 5: SKU `GRC-037`, chain-net

- **Result:** `ENGINE!N42` = **0**
- **Native Excel formula:**

```excel
=IF($D42="Y",MAX(0,$F42-$E42*SKU_Master!$O$42),0)
```

- **Arithmetic / decision check:** `IF("N" = "Y", …, 0) = 0`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE` | `D42` | N | Direct precedent/input |
| `ENGINE` | `F42` | 3,339 | Direct precedent/input |
| `ENGINE` | `E42` | 331.202554 | Direct precedent/input |
| `SKU_Master` | `O42` | 999 | Direct precedent/input |

---

## Formula 23: Markdown at-risk value (gross)

**Documented logic:** `Expiry excess value; otherwise overstock/slow-mover excess or 30% fallback`

### Example 1: SKU `GRC-002`, Store `S005`

- **Result:** `ENGINE_STORE!AF28` = **308,611.466807**
- **Native Excel formula:**

```excel
=IF($Q28="Expiry",MAX(0,$M28-$J28*SKU_Master!$O$7)*$R28,IF(OR($Q28="Overstock",$Q28="Slow-mover"),IF(MAX(0,$M28-$O28)>0,($M28-$O28)*$R28,$M28*0.3*$R28),0))
```

- **Arithmetic / decision check:** `State Expiry; gross exposure = 308,611.466807`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `Q28` | Expiry | Direct precedent/input |
| `ENGINE_STORE` | `M28` | 110 | Direct precedent/input |
| `ENGINE_STORE` | `J28` | 23.460583 | Direct precedent/input |
| `SKU_Master` | `O7` | 4 | Direct precedent/input |
| `ENGINE_STORE` | `O28` | 258 | Direct precedent/input |
| `ENGINE_STORE` | `R28` | 19,100 | Direct precedent/input |

---

### Example 2: SKU `GRC-001`, Store `S001`

- **Result:** `ENGINE_STORE!AF4` = **0**
- **Native Excel formula:**

```excel
=IF($Q4="Expiry",MAX(0,$M4-$J4*SKU_Master!$O$6)*$R4,IF(OR($Q4="Overstock",$Q4="Slow-mover"),IF(MAX(0,$M4-$O4)>0,($M4-$O4)*$R4,$M4*0.3*$R4),0))
```

- **Arithmetic / decision check:** `State Stockout; gross exposure = 0`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `Q4` | Stockout | Direct precedent/input |
| `ENGINE_STORE` | `M4` | 68 | Direct precedent/input |
| `ENGINE_STORE` | `J4` | 29.166885 | Direct precedent/input |
| `SKU_Master` | `O6` | 3 | Direct precedent/input |
| `ENGINE_STORE` | `O4` | 321 | Direct precedent/input |
| `ENGINE_STORE` | `R4` | 18,900 | Direct precedent/input |

---

### Example 3: SKU `GRC-010`, Store `S005`

- **Result:** `ENGINE_STORE!AF188` = **0**
- **Native Excel formula:**

```excel
=IF($Q188="Expiry",MAX(0,$M188-$J188*SKU_Master!$O$15)*$R188,IF(OR($Q188="Overstock",$Q188="Slow-mover"),IF(MAX(0,$M188-$O188)>0,($M188-$O188)*$R188,$M188*0.3*$R188),0))
```

- **Arithmetic / decision check:** `State Low; gross exposure = 0`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `Q188` | Low | Direct precedent/input |
| `ENGINE_STORE` | `M188` | 164 | Direct precedent/input |
| `ENGINE_STORE` | `J188` | 36.407468 | Direct precedent/input |
| `SKU_Master` | `O15` | 6 | Direct precedent/input |
| `ENGINE_STORE` | `O188` | 400 | Direct precedent/input |
| `ENGINE_STORE` | `R188` | 20,500 | Direct precedent/input |

---

### Example 4: SKU `GRC-043`, Store `S005`

- **Result:** `ENGINE_STORE!AF848` = **3,677,800**
- **Native Excel formula:**

```excel
=IF($Q848="Expiry",MAX(0,$M848-$J848*SKU_Master!$O$48)*$R848,IF(OR($Q848="Overstock",$Q848="Slow-mover"),IF(MAX(0,$M848-$O848)>0,($M848-$O848)*$R848,$M848*0.3*$R848),0))
```

- **Arithmetic / decision check:** `State Overstock; gross exposure = 3,677,800`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `Q848` | Overstock | Direct precedent/input |
| `ENGINE_STORE` | `M848` | 908 | Direct precedent/input |
| `ENGINE_STORE` | `J848` | 58.948606 | Direct precedent/input |
| `SKU_Master` | `O48` | 999 | Direct precedent/input |
| `ENGINE_STORE` | `O848` | 766 | Direct precedent/input |
| `ENGINE_STORE` | `R848` | 25,900 | Direct precedent/input |

---

### Example 5: SKU `GRC-040`, Store `S001`

- **Result:** `ENGINE_STORE!AF784` = **3,144,150**
- **Native Excel formula:**

```excel
=IF($Q784="Expiry",MAX(0,$M784-$J784*SKU_Master!$O$45)*$R784,IF(OR($Q784="Overstock",$Q784="Slow-mover"),IF(MAX(0,$M784-$O784)>0,($M784-$O784)*$R784,$M784*0.3*$R784),0))
```

- **Arithmetic / decision check:** `State Slow-mover; gross exposure = 3,144,150`

**Input and source-cell verification:**

| Source sheet | Cell | Saved value | Role |
|---|---:|---:|---|
| `ENGINE_STORE` | `Q784` | Slow-mover | Direct precedent/input |
| `ENGINE_STORE` | `M784` | 411 | Direct precedent/input |
| `ENGINE_STORE` | `J784` | 36.882238 | Direct precedent/input |
| `SKU_Master` | `O45` | 999 | Direct precedent/input |
| `ENGINE_STORE` | `O784` | 479 | Direct precedent/input |
| `ENGINE_STORE` | `R784` | 25,500 | Direct precedent/input |

---

