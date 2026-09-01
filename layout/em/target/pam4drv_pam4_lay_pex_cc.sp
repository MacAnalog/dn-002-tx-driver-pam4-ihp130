*********************************************************
*** NGSPICE file created by KLayout-PEX 0.3.12
*** -----------------------------------------------------
***     Extraction Engine: KPEX/2.5D
***     Technology: ihp_sg13g2
***     Date: 2026-08-31 23:45:36
*********************************************************

.SUBCKT pam4drv_pam4_lay sub msbn lsbp vcmb lsbn msbp tmsb0 tmsb1 tlsb0 vcasc
+ outp outn vcc
Q$1 \$37 msbp \$10 sub npn13G2 we=0.07 le=0.9 Nx=3 m=1
Q$2 \$38 msbn \$11 sub npn13G2 we=0.07 le=0.9 Nx=3 m=1
Q$3 \$39 msbp \$12 sub npn13G2 we=0.07 le=0.9 Nx=3 m=1
Q$4 \$40 msbn \$13 sub npn13G2 we=0.07 le=0.9 Nx=3 m=1
Q$5 \$41 lsbp \$14 sub npn13G2 we=0.07 le=0.9 Nx=3 m=1
Q$6 \$42 lsbn \$15 sub npn13G2 we=0.07 le=0.9 Nx=3 m=1
Q$7 outp vcasc \$37 sub npn13G2 we=0.07 le=0.9 Nx=3 m=1
Q$8 outn vcasc \$38 sub npn13G2 we=0.07 le=0.9 Nx=3 m=1
Q$9 outp vcasc \$39 sub npn13G2 we=0.07 le=0.9 Nx=3 m=1
Q$10 outn vcasc \$40 sub npn13G2 we=0.07 le=0.9 Nx=3 m=1
Q$11 outp vcasc \$41 sub npn13G2 we=0.07 le=0.9 Nx=3 m=1
Q$12 outn vcasc \$42 sub npn13G2 we=0.07 le=0.9 Nx=3 m=1
R$13 vcmb lsbp sub 0.68 rsil l=3.41 ps=0 b=0 m=1
R$14 vcmb lsbn sub 0.68 rsil l=3.41 ps=0 b=0 m=1
R$15 vcmb msbp sub 0.68 rsil l=3.41 ps=0 b=0 m=1
R$16 vcmb msbn sub 0.68 rsil l=3.41 ps=0 b=0 m=1
R$17 tmsb0 \$10 sub 5.66 rsil l=1.21 ps=0 b=0 m=1
R$18 tmsb0 \$11 sub 5.66 rsil l=1.21 ps=0 b=0 m=1
R$19 tmsb1 \$12 sub 5.66 rsil l=1.21 ps=0 b=0 m=1
R$20 tmsb1 \$13 sub 5.66 rsil l=1.21 ps=0 b=0 m=1
R$21 tlsb0 \$14 sub 5.66 rsil l=1.21 ps=0 b=0 m=1
R$22 tlsb0 \$15 sub 5.66 rsil l=1.21 ps=0 b=0 m=1
R$23 outp vcc sub 1.51 rsil l=9.88 ps=0 b=0 m=1
R$24 outn vcc sub 1.51 rsil l=9.88 ps=0 b=0 m=1
Cext_1 \$10 \$11 497.458a
Cext_2 \$10 \$37 1.33983f
Cext_3 \$10 \$38 23.6258a
Cext_4 \$10 msbn 3.19999a
Cext_5 \$10 msbp 739.396a
Cext_6 \$10 sub 11.1408a
Cext_7 \$10 tmsb0 273.289a
Cext_8 \$10 vcasc 13.5074a
Cext_9 \$10 VSUBS 3.13381f
Cext_10 \$11 \$37 0.596619a
Cext_11 \$11 \$38 1.32679f
Cext_12 \$11 msbn 731.632a
Cext_13 \$11 msbp 11.8595a
Cext_14 \$11 sub 4.63658a
Cext_15 \$11 tmsb0 259.593a
Cext_16 \$11 vcasc 5.98964a
Cext_17 \$11 VSUBS 2.86367f
Cext_18 \$12 \$13 497.458a
Cext_19 \$12 \$39 1.33983f
Cext_20 \$12 \$40 23.6258a
Cext_21 \$12 msbn 3.19999a
Cext_22 \$12 msbp 739.242a
Cext_23 \$12 sub 4.63658a
Cext_24 \$12 tmsb1 273.289a
Cext_25 \$12 vcasc 13.5074a
Cext_26 \$12 VSUBS 3.13597f
Cext_27 \$13 \$39 0.596619a
Cext_28 \$13 \$40 1.32679f
Cext_29 \$13 msbn 731.632a
Cext_30 \$13 msbp 0.699289a
Cext_31 \$13 sub 4.63658a
Cext_32 \$13 tmsb1 259.593a
Cext_33 \$13 vcasc 5.98964a
Cext_34 \$13 VSUBS 2.86367f
Cext_35 \$14 \$15 497.458a
Cext_36 \$14 \$41 1.33983f
Cext_37 \$14 \$42 23.6258a
Cext_38 \$14 lsbn 3.19999a
Cext_39 \$14 lsbp 727.79a
Cext_40 \$14 sub 4.63658a
Cext_41 \$14 tlsb0 273.289a
Cext_42 \$14 vcasc 13.5074a
Cext_43 \$14 VSUBS 3.1377f
Cext_44 \$15 \$41 0.596619a
Cext_45 \$15 \$42 1.32679f
Cext_46 \$15 lsbn 731.632a
Cext_47 \$15 lsbp 0.699289a
Cext_48 \$15 sub 8.72568a
Cext_49 \$15 tlsb0 259.593a
Cext_50 \$15 vcasc 5.98964a
Cext_51 \$15 VSUBS 2.86305f
Cext_52 \$37 msbp 50.8262a
Cext_53 \$37 outp 736.362a
Cext_54 \$37 sub 19.5924a
Cext_55 \$37 vcasc 750.584a
Cext_56 \$37 VSUBS 2.24299f
Cext_57 \$38 msbn 50.8262a
Cext_58 \$38 outn 676.029a
Cext_59 \$38 outp 60.1788a
Cext_60 \$38 sub 26.6745a
Cext_61 \$38 vcasc 761.307a
Cext_62 \$38 VSUBS 2.23444f
Cext_63 \$39 msbp 50.8262a
Cext_64 \$39 outp 750.525a
Cext_65 \$39 sub 26.6745a
Cext_66 \$39 vcasc 761.307a
Cext_67 \$39 VSUBS 2.23444f
Cext_68 \$40 msbn 50.8262a
Cext_69 \$40 outn 676.029a
Cext_70 \$40 outp 60.1788a
Cext_71 \$40 sub 26.6745a
Cext_72 \$40 vcasc 761.307a
Cext_73 \$40 VSUBS 2.23444f
Cext_74 \$41 lsbp 50.8262a
Cext_75 \$41 outp 736.362a
Cext_76 \$41 sub 26.6745a
Cext_77 \$41 vcasc 761.307a
Cext_78 \$41 VSUBS 2.23444f
Cext_79 \$42 lsbn 50.8262a
Cext_80 \$42 outn 676.029a
Cext_81 \$42 sub 15.5717a
Cext_82 \$42 vcasc 743.997a
Cext_83 \$42 VSUBS 2.24969f
Cext_84 lsbn lsbp 394.686a
Cext_85 lsbn msbn 31.3713a
Cext_86 lsbn msbp 67.7154a
Cext_87 lsbn sub 28.2829a
Cext_88 lsbn tlsb0 77.186a
Cext_89 lsbn vcmb 109.516a
Cext_90 lsbp msbn 383.545a
Cext_91 lsbp msbp 58.1687a
Cext_92 lsbp tlsb0 77.186a
Cext_93 lsbp vcmb 8.515a
Cext_94 msbn msbp 654.199a
Cext_95 msbn tmsb0 77.3391a
Cext_96 msbn tmsb1 117.426a
Cext_97 msbn vcmb 8.515a
Cext_98 msbp sub 22.931a
Cext_99 msbp tmsb0 261.724a
Cext_100 msbp tmsb1 207.053a
Cext_101 msbp vcmb 8.515a
Cext_102 outn outp 1.69232f
Cext_103 outn sub 139.575a
Cext_104 outn vcasc 152.2a
Cext_105 outn vcc 2.8452a
Cext_106 outp sub 180.804a
Cext_107 outp vcasc 227.655a
Cext_108 outp vcc 2.8452a
Cext_109 sub tlsb0 9.33102a
Cext_110 sub tmsb0 10.5322a
Cext_111 sub vcasc 372.601a
Cext_112 sub vcc 772.209a
Cext_113 sub vcmb 888.861a
Cext_114 VSUBS lsbn 5.28596f
Cext_115 VSUBS lsbp 3.96187f
Cext_116 VSUBS msbn 6.04947f
Cext_117 VSUBS msbp 6.53f
Cext_118 VSUBS outn 12.0949f
Cext_119 VSUBS outp 11.2501f
Cext_120 VSUBS sub 45.7247f
Cext_121 VSUBS tlsb0 4.06166f
Cext_122 VSUBS tmsb0 4.06009f
Cext_123 VSUBS tmsb1 4.04937f
Cext_124 VSUBS vcasc 7.0258f
Cext_125 VSUBS vcc 8.9016f
Cext_126 VSUBS vcmb 9.636f
.ENDS pam4drv_pam4_lay
